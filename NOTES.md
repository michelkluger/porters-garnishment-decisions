# Notes: next steps, risks, open decisions

## Open decisions (not resolved on purpose; we figure these out together)

Each runs the safe default today and is marked `OPEN` or `TODO(brand)` in the code.

1. **Missing IBAN.** Now `needs_human` (`ACCOUNT_IBAN_MISSING`): without it the bank matches the debtor to an
   account by name, which is a human's call. The brief only says it must not force a reject; it could allow
   `auto` when everything else is clean.
2. **Missing debtor name.** Now `needs_human`. The brief's reject examples are about amount and case
   reference; a missing debtor may be a reject instead.
3. **Case-reference format.** Implemented as the spec's words, `[A-Z]{2}-\d+/\d+`. The example `XX-0000/00`
   suggests exactly 4 and 2 digits. Stricter means more rejects of real letters if courts vary.
4. **Model and provider.** Default `anthropic:claude-haiku-5-5` at its default effort (`medium`); any Pydantic
   AI model string works via `PORTERS_MODEL`. Measured on the 9 samples (2026-11-03): Haiku 5.5 and Opus 5.5
   gave the same route, deciding rule, fields and confidences on every letter, including the embedded
   instruction; Haiku cost about $0.0004 per letter against $0.014 (~1/36) and was no slower. Nine letters
   cannot show rare errors: before production, compare both on a larger labelled set, counting false `auto`
   first.
5. **Refusals.** A model refusal currently becomes `EXTRACTION_FAILED` → `needs_human`. Anthropic's
   server-side refusal fallback was not enabled: I could not test it here, and a wrong parameter would break
   every call.
6. **Brand.** Roobert (their typeface) is licensed, so it is listed but not bundled; the logo is a text
   wordmark; the amber and red route colours are not from their palette. All three need Porters' input.
7. **Duplicate letters.** Not detected today: the same letter posted twice gives two decisions, possibly two
   `auto`. Courts resend letters, so this matters before execution exists. Options: route a repeat to
   `needs_human` (`DUPLICATE_LETTER`), or return the first decision. What counts as "the same" (exact text, same
   case reference + amount) is the open part.
8. **Copyright header.** Ruff runs with every rule except `CPY001` (copyright notice in each file), because
   who holds the copyright and under which licence is not decided. Pick both, then drop it from `ignore`.
9. **Docstrings on the LLM contract.** The six classes the model fills in (`Status` … `Extraction` in
   `schema.py`) carry `noqa: D101`: Pydantic sends class docstrings to the model as schema descriptions, so
   adding them changes the prompt. Add them with a `PROMPT_VERSION` bump and a paid `test_samples_llm` run.
10. **Letter size limit.** `POST /decisions` accepts up to 50,000 characters (about 12,000 input tokens). Real
   letters of one to three pages are a few thousand characters, so a lower limit would cut what one abusive
   request can cost, at the risk of refusing a long genuine letter. Which length to allow is open.

## Next steps

1. Re-record the demo readings through the app's own extractor: `uv run python -m scripts.record_samples` in
   `backend/` (needs a key, under 1¢). Today's recordings come from a Claude Code subagent given the same
   prompt, not from the app's model call, and that run missed the printed case reference on letters 7 and 8
   (the rules caught both as `CASE_REFERENCE_MISSED`). Then run `PORTERS_LLM_TESTS=1` on every prompt or model
   change: each sample must route as labelled and fire the rule it exists to test.
2. Build a labelled set of real (anonymised) letters, then report a route confusion matrix. The numbers that
   matter: false `auto` (target 0), then false `reject`, then the `needs_human` rate (the cost). Size it for
   the claim: zero false `auto` in n letters only bounds the rate below about 3/n (95%), so showing it is under
   0.1% takes about 3,000 `auto` decisions with none wrong. The 9 samples are a regression gate, not evidence.
3. Shadow mode: run beside the clerks and compare routes. Switch `auto` on only after a clean period; that
   period is the evidence the rules work.
4. Self-consistency: two extractions, any disagreement → `needs_human`. Measure its catch rate against cost.
5. Reviewer loop: a `needs_human` queue whose corrections become new labels and new test cases.
6. Case linking: check a restriction against the stored original order (same case reference, prior amount).

## Risks

- Prompt run live only once, over 9 samples. The rules are tested against hand-built extractions and replayed
  readings. Mitigation: step 1 above, then keep the sample suite as a regression gate on every prompt or model
  change.
- Overconfident wrong extraction that passes every check. A grounded, well-formed, wrong value, e.g. the
  wrong one of two names that are both in the letter. Names are the weak spot: a second IBAN or case reference
  printed in the letter is found by the code's own scan, a second name only if the model lists it. The
  candidates list and self-consistency narrow this; only labelled data measures it.
- Instructions written in a letter are not flagged by any rule. They cannot pick the route, and every value
  must still be found in the letter (sample 9 is caught by its hedged amount, not by its instruction), but an
  instruction could steer the model to the wrong one of two names. A rule that sends such letters to a human
  needs a prompt change (the model quoting any instruction it sees), so a `PROMPT_VERSION` bump and a paid run.
- Grounding is whole-word substring matching. Robust to whitespace, not to case, OCR noise or reformatting. Fine
  for `.txt`, insufficient once scans arrive.
- Number formats. Only `4,250.00` style is parsed. A European `4.250,00` fails the value-vs-quote check
  and goes to a human (safe, but noisy). Marked `shortcut:` in `rules.py`.
- IBAN check is shape + mod-97, with no per-country length table. Also a `shortcut:` comment.
- Rule changes vs old decisions: each record stores `rules_version` and `prompt_version`, but there is no
  migration or replay tooling yet, and no Alembic: the schema is created on startup. `GET /decisions/{id}`
  rebuilds the stored decision JSON into today's `DecisionResponse`, so a breaking change to `Decision` would
  make old records unreadable. Version the readers along with the migrations.
- Sync rules and SQLite calls run in a worker thread (`asyncio.to_thread`), not on the event loop. Fine at
  prototype volume; move to a worker queue or an async driver under real load.
- A hung model call holds its request for up to about a minute and a half (30 s timeout per attempt, two
  Anthropic SDK retries) before it fails to a human. Fine for the workbench; a queue takes it off the request.
- Exposed as is, the API is a paid LLM for anyone who can reach it: no login, no rate limit, and the response
  returns the model's raw reading, whose free-text fields (`role`, `value`, quotes) a "letter" can ask the model
  to fill with an answer to anything. Today both servers listen on 127.0.0.1 only, and a reading is capped at
  2,000 output tokens. Before any deployment: authentication, a per-caller rate limit, a spend limit on the API
  key, and an alert on `cost_usd` (already stored per decision).
- Demo mode switches on by itself when no key is set. That's convenient for a prototype. In production, set
  `PORTERS_EXTRACTOR=llm`, and the app refuses to start without a key.
- Letters contain personal data and are stored in plain SQLite with no retention policy. Not acceptable
  beyond a prototype.
