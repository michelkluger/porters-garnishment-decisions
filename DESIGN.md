# Design

## The problem, as framed

A bank receives court orders to seize a customer's funds. Today a clerk reads each one and makes one call:
act on it, have a second person check it, or reject it. A wrong call is a regulated incident, so the call must
be explainable afterwards. We automate **that call only**: not the seizure itself.

The core tension: extraction is probabilistic, the decision must be deterministic and defensible. So the
design draws one hard line: **the model reads, the code decides.** The model never outputs a route.

## Requirements and scope

In scope:
- extract `debtor_name`, `amount`, `case_reference`, `account_iban` with a real LLM, behind an interface;
- route with explicit rules: same extraction + same letter = same route, always;
- persist every decision with the values, per-field confidence, every rule (fired or not) and the route;
- `POST /decisions`, `GET /decisions/{id}`;
- a small drag-and-drop page to test letters by hand (added on request; not part of the brief's scope).

Out of scope (deliberately): executing, booking or reversing a seizure; idempotency / duplicate letters;
multi-tenancy; authentication; OCR and PDFs (the page accepts `.txt` only); queueing; linking letters of the
same case; data retention and PII handling.

## Where confidence comes from

I do not ask the model for a numeric confidence. Self-reported numbers are uncalibrated (models say 0.95 for
nearly everything), so a threshold on them cannot be defended. Instead, per field, the model reports
**evidence**, and the code checks it:

| From the model | Checked by code |
|---|---|
| `value` | does it parse, is it well-formed (case-reference pattern, IBAN mod-97, amount > 0, printed as EUR in the letter) |
| `source_quote`, copied verbatim | is the quote really in the letter (catches hallucination and injection) |
| `status`: explicit / approximate / partial / ambiguous / absent | does the value follow from its quote |
| `other_candidates` with a role | the code scans the letter for every EUR figure and requires each to be accounted for; a rival not among those figures is ignored |

A field's **confidence** is the outcome of those rules: `high` (all passed), `low` (a rule sent it to a
human), `invalid` (a hard validation failed), `absent`. Every rule result is stored with a plain-language
detail, so "why" is never reconstructed, it is read.

**The threshold is zero tolerance:** `auto` requires every rule to pass. The costs are asymmetric: a wrong
`auto` is an incident; a wrong `needs_human` costs a clerk a minute, and clerks read every letter today, so
any `auto` is already a gain. Start strict, loosen only with measured evidence (see NOTES).

**A reject is also an automatic decision**, and ignoring a valid order is an incident too. So rejects fire
only on evidence that is printed in the letter: "no amount" needs both the model *and* the code's own scan to
find none; a malformed case reference must appear verbatim in the letter; "not a garnishment" is the model's
judgement, so it rejects only a letter that cites no EUR sum. A model that says "absent" while the letter
contains a figure is a *miss* and goes to a human, not to reject.

## The rules (`backend/app/decisions/rules.py`, rules version 2)

All rules are always evaluated; the route is the most severe that fired (reject > needs_human > auto); the
first such rule in a fixed order is the `primary_rule`.

- **Reject:** `NOT_A_GARNISHMENT`, `CASE_REFERENCE_MISSING`, `CASE_REFERENCE_MALFORMED`, `AMOUNT_MISSING`,
  `AMOUNT_NOT_POSITIVE`. Each only on grounded evidence, as above.
- **Needs human, per field:** `*_NOT_IN_LETTER` (quote not found; case-sensitive, spacing-tolerant),
  `*_VALUE_NOT_IN_QUOTE` (misread; a name or case reference must appear whole and exactly as written, so
  `AB-1042/2` is not in `AB-1042/24`), `*_UNCERTAIN` (model said approximate/partial/ambiguous),
  `*_HAS_ALTERNATIVES` (rival values for a single-valued field), `*_MISSED` (model says absent, letter has it).
- **Needs human, field-specific:** `DEBTOR_NAME_PARTIAL` (initial-only, one word, or title + surname),
  `AMOUNT_NOT_A_FIGURE`, `AMOUNT_HEDGED`, `AMOUNT_NOT_EUR`, `AMOUNT_UNEXPLAINED_FIGURES`,
  `RESTRICTION_NOT_REDUCING`, `ACCOUNT_IBAN_INVALID`, `ACCOUNT_IBAN_MISSING`, `DEBTOR_NAME_MISSING`,
  `DOCUMENT_TYPE_NOT_IN_LETTER`, `NOT_A_GARNISHMENT_UNCONFIRMED` (model says "not a garnishment", but the letter
  cites an EUR sum).
- **Needs human, system:** `EXTRACTION_FAILED` (model down, refusal, schema-invalid output), `RULES_FAILED`
  (a bug in the rules; also returned as `500`).

Several rules are deterministic backstops for an overconfident model: `DEBTOR_NAME_PARTIAL` and
`AMOUNT_NOT_A_FIGURE` fire even when the model claims "explicit", and `AMOUNT_NOT_EUR` fires when the model
says EUR but the figure is not printed as EUR in the letter.

How the samples come out: letter 1 → nothing fires → `auto`. Letter 2 → partial name, prose amount, hedge,
no IBAN → `needs_human` (not reject: an amount is present, only inexact). Letter 3 → two figures; the model
names 1,267 operative and 4,250 superseded, 1,267 < 4,250, all figures accounted for → `auto`. A reading
that takes 4,250 trips `RESTRICTION_NOT_REDUCING`; one that ignores the other figure trips
`AMOUNT_UNEXPLAINED_FIGURES`; an unsure one trips `AMOUNT_UNCERTAIN`. None of this keys on sample wording.

## Data model and API contract

One append-only SQLite table, `decisions` (`backend/app/decisions/models.py`): `id`, `created_at`, `route`,
`primary_rule`, `case_reference` (indexed columns for filtering), `letter_text` (needed to re-run grounding
checks), `extraction` (model output as received, JSON), `decision` (per-field evidence and every rule, JSON),
`model`, `prompt_version`, `rules_version`, `error`. JSON columns rather than evidence tables because the
evidence is always read whole. Rows are never updated.

`POST /decisions {"text": "..."}` → `201` with the full decision. `GET /decisions/{id}` → the same record
from disk, `404` if unknown. Input is validated at the boundary (non-blank, ≤ 50,000 characters → `422`).

## Key decisions and alternatives weighed

- **Evidence + code checks vs model-reported confidence numbers:** above. A number may be added later as one
  more recorded signal, but routed on only once calibrated against real outcomes.
- **One model call vs asking twice and comparing (self-consistency):** disagreement is a strong uncertainty
  signal, but it doubles cost and latency. The grounding checks catch most of what it would. First upgrade.
- **Fail to human on model errors**, not `503`: the letter is stored and routed; nothing is lost. Bugs in the
  rules, by contrast, stay a loud `500`, so they are not hidden behind `needs_human`; the letter is still stored
  first (`RULES_FAILED`), so it is not lost either.
- **Prompt injection:** the letter is wrapped and declared untrusted, but the real defence is structural:
  the model cannot pick the route, every value must be found in the letter, and its document type alone cannot
  reject a letter that cites an EUR sum.
- **Pydantic AI + native structured output** (requested): the model's answer is schema-constrained, the
  provider is a config string, and the `Extractor` protocol keeps the rules testable without any model.
- **Layered backend, one package per domain** (`app/decisions/`): router (HTTP) → service (use case) →
  `llm_client` (model), `rules` (pure logic), `repository` (SQL). Each layer depends only on the ones below it, so
  the model, the database or the web framework can be swapped or faked without touching the rules, and a second
  domain (say, account-freeze letters) is a sibling package rather than a growing file. The alternative, one
  flat module per concern, is fewer files today but mixes the domains as soon as there are two.
- **Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.1, pytest, as recommended. Python 3.14, not 3.15: a
  dependency has no 3.15 wheels on Windows yet. Frontend on Bun (its dev server forwards `/api`, so no CORS
  setup) with React 19, shadcn/ui and Tailwind 4, themed with tokens from withporters.com's stylesheet.

## Work breakdown

Built first, in this order: (1) rules and their table of tests, which needs no model; (2) extraction schema,
prompt and extractor; (3) storage and API; (4) test page; (5) docs.

The full build after this slice: a labelled evaluation set of real letters and a shadow-mode run against
clerks → threshold tuning from that data → reviewer queue for `needs_human` with corrections fed back as
labels → idempotency and case linking (restriction ↔ original order) → OCR/PDF intake → auth, audit export,
retention → execution, in a separate service with its own controls.

## Where I deliberately stopped

At the decision. The rules have not been tuned on real letters: the samples are three given plus six I wrote,
and the prompt has not yet been run against the real model (no key in this environment). Open decisions I did
not resolve on my own are listed in `NOTES.md`; where code needed some behaviour, it takes the safe side
(`needs_human`) and is marked `OPEN` in a comment.
