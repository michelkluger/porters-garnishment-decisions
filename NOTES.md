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
4. **Model and provider.** Default `anthropic:claude-opus-5-5` at its default effort (`medium`); any Pydantic
   AI model string works via `PORTERS_MODEL`. Cost/quality per letter not measured yet.
5. **Refusals.** A model refusal currently becomes `EXTRACTION_FAILED` → `needs_human`. Anthropic's
   server-side refusal fallback was not enabled: I could not test it here, and a wrong parameter would break
   every call.
6. **Brand.** Roobert (their typeface) is licensed, so it is listed but not bundled; the logo is a text
   wordmark; the amber and red route colours are not from their palette. All three need Porters' input.
7. **Duplicate letters.** Not detected today: the same letter posted twice gives two decisions, possibly two
   `auto`. Courts resend letters, so this matters before execution exists. Options: route a repeat to
   `needs_human` (`DUPLICATE_LETTER`), or return the first decision. What counts as "the same" (exact text, same
   case reference + amount) is the open part.

## Next steps

1. **Run the real model over `samples/`** (`PORTERS_LLM_TESTS=1`) and fix the prompt where a sample misroutes.
   Not done yet: no key in this environment. This is the biggest gap.
2. **Build a labelled set of real (anonymised) letters**, then report a route confusion matrix. The numbers that
   matter: false `auto` (target 0), then false `reject`, then the `needs_human` rate (the cost).
3. **Shadow mode:** run beside the clerks, compare routes, switch `auto` on only after a clean period. This is
   how we would know the rules are right, rather than believing it.
4. **Self-consistency:** two extractions, any disagreement → `needs_human`. Measure its catch rate against cost.
5. **Reviewer loop:** a `needs_human` queue whose corrections become new labels and new test cases.
6. **Case linking:** check a restriction against the stored original order (same case reference, prior amount).

## Risks

- **Prompt untested against the live model.** The rules are tested against hand-built extractions only.
  Mitigation: step 1 above, then keep the sample suite as a regression gate on every prompt or model change.
- **Overconfident wrong extraction that passes every check.** A grounded, well-formed, wrong value, e.g. the
  wrong one of two names that are both in the letter. The candidates list and self-consistency narrow this;
  only labelled data measures it.
- **Grounding is substring matching.** Robust to whitespace, not to case, OCR noise or reformatting. Fine
  for `.txt`, insufficient once scans arrive.
- **Number formats.** Only `4,250.00` style is parsed. A European `4.250,00` fails the value-vs-quote check
  and goes to a human (safe, but noisy). Marked `shortcut:` in `rules.py`.
- **IBAN check is shape + mod-97**, with no per-country length table. Also a `shortcut:` comment.
- **Rule changes vs old decisions:** each record stores `rules_version` and `prompt_version`, but there is no
  migration or replay tooling yet, and no Alembic: the schema is created on startup.
- **Sync SQLite calls inside an async endpoint.** Fine at prototype volume; move to a worker queue or an async
  driver under real load.
- **Demo mode switches on by itself when no key is set.** That's convenient for a prototype, but in production a
  missing key must stop startup, not quietly replay recordings. Set `PORTERS_EXTRACTOR=llm` explicitly there.
- **Letters contain personal data** and are stored in plain SQLite with no retention policy. Not acceptable
  beyond a prototype.
