"""Deterministic routing: (letter text, extraction) -> decision.

Pure functions only: no I/O, no clock, no randomness, so the same input always gives the same route.
Every rule is evaluated and recorded, fired or not; the route is the most severe one that fired.
"""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from .schema import (
    Confidence, Decision, DocumentType, ExtractedField, Extraction, FieldEvidence, Route, RuleResult, Status,
)

RULES_VERSION = "1"

NH, REJECT = Route.NEEDS_HUMAN, Route.REJECT
_SEVERITY = {Route.AUTO: 0, Route.NEEDS_HUMAN: 1, Route.REJECT: 2}
_UNCERTAIN = {Status.APPROXIMATE, Status.PARTIAL, Status.AMBIGUOUS}

# shortcut: English number format only ("4,250.00"); "4.250,00" fails the value-vs-quote check
# and goes to a human. Upgrade when letters arrive in other locales.
_FIGURE = r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_EUR_AMOUNT = re.compile(rf"(?:EUR|€)\s*({_FIGURE})|({_FIGURE})\s*(?:€|(?:EUR|euros?)\b)", re.I)
_HEDGE = re.compile(r"\b(?:approx\w*|about|around|circa|roughly|estimated|in the region of|or so)\b", re.I)
_CASE_REF = re.compile(r"[A-Z]{2}-\d+/\d+")  # spec: two letters, digits, slash, digits
_INITIAL = re.compile(r"[^\W\d_]\.?")


def _norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", s).split()).casefold()


def _in(fragment: str | None, text: str) -> bool:
    return bool(fragment) and _norm(fragment) in _norm(text)


def _dec(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(",", "").strip())
    except InvalidOperation:
        return None


def _figures(s: str) -> set[Decimal]:
    return {d for m in re.findall(_FIGURE, s) if (d := _dec(m)) is not None}


def _eur_amounts(text: str) -> set[Decimal]:
    return {d for a, b in _EUR_AMOUNT.findall(text) if (d := _dec(a or b)) is not None}


def _compact(s: str) -> str:
    return re.sub(r"\s", "", s).upper()


def _iban_valid(value: str) -> bool:
    # shortcut: generic shape + mod-97 only, no per-country length table. Add one if non-DE IBANs matter.
    s = _compact(value)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    return int("".join(str(int(c, 36)) for c in s[4:] + s[:4])) % 97 == 1


def _rule(rule: str, field: str | None, fired: bool, route: Route, if_fired: str, if_not: str) -> RuleResult:
    return RuleResult(rule=rule, field=field, fired=fired, route=route, detail=if_fired if fired else if_not)


def _present(f: ExtractedField) -> bool:
    return f.status is not Status.ABSENT and bool(f.value and f.value.strip())


def _common(name: str, f: ExtractedField, text: str) -> list[RuleResult]:
    """Rules every present field must pass: its quote is really in the letter and the model was sure."""
    tag = name.upper()
    return [
        _rule(f"{tag}_NOT_IN_LETTER", name, not _in(f.source_quote, text), NH,
              f"quote {f.source_quote!r} does not appear in the letter", "quote found in the letter"),
        _rule(f"{tag}_UNCERTAIN", name, f.status in _UNCERTAIN, NH,
              f"model marked it {f.status}", "model marked it explicit"),
    ]


def _single_value(name: str, f: ExtractedField) -> RuleResult:
    """Name, case reference and IBAN have exactly one right answer; any rival means ambiguity."""
    rivals = [c.value for c in f.other_candidates]
    return _rule(f"{name.upper()}_HAS_ALTERNATIVES", name, bool(rivals), NH,
                 f"other possible values in the letter: {rivals}", "no other possible values")


def _debtor_name(f: ExtractedField, text: str) -> list[RuleResult]:
    name = "debtor_name"
    if not _present(f):
        # OPEN: the spec lists no-amount and bad case reference as rejects, not a missing name.
        # Sent to a human until that is agreed.
        return [_rule("DEBTOR_NAME_MISSING", name, True, NH, "no debtor name in the letter", "")]
    tokens = f.value.split()
    partial = len(tokens) < 2 or bool(_INITIAL.fullmatch(tokens[0]))
    return [
        *_common(name, f, text),
        _rule("DEBTOR_NAME_VALUE_NOT_IN_QUOTE", name, not _in(f.value, f.source_quote or ""), NH,
              f"{f.value!r} is not what the quote says", "value matches its quote"),
        _rule("DEBTOR_NAME_PARTIAL", name, partial, NH,
              f"{f.value!r} is not a full name (single word or initial only)", "full name"),
        _single_value(name, f),
    ]


def _case_reference(f: ExtractedField, text: str) -> list[RuleResult]:
    name = "case_reference"
    if not _present(f):
        in_text = _CASE_REF.findall(text)
        if in_text:
            return [_rule("CASE_REFERENCE_MISSED", name, True, NH,
                          f"model found none, but the letter contains {in_text}", "")]
        return [_rule("CASE_REFERENCE_MISSING", name, True, REJECT, "no case reference in the letter", "")]
    malformed = not _CASE_REF.fullmatch(f.value.strip())
    return [
        *_common(name, f, text),
        _rule("CASE_REFERENCE_VALUE_NOT_IN_QUOTE", name, not _in(f.value, f.source_quote or ""), NH,
              f"{f.value!r} is not what the quote says", "value matches its quote"),
        # Reject only when the malformed value is really printed in the letter, not a misread.
        _rule("CASE_REFERENCE_MALFORMED", name, malformed and _in(f.value, text), REJECT,
              f"{f.value!r} is not in the format XX-0000/00", "format XX-0000/00"),
        _single_value(name, f),
    ]


def _account_iban(f: ExtractedField, text: str) -> list[RuleResult]:
    name = "account_iban"
    if not _present(f):
        # OPEN: the spec only says a missing IBAN must not force a reject. Without it the bank must
        # match the debtor to an account by name, so it goes to a human until agreed otherwise.
        return [_rule("ACCOUNT_IBAN_MISSING", name, True, NH, "no IBAN in the letter", "")]
    return [
        *_common(name, f, text),
        _rule("ACCOUNT_IBAN_VALUE_NOT_IN_QUOTE", name, _compact(f.value) not in _compact(f.source_quote or ""), NH,
              f"{f.value!r} is not what the quote says", "value matches its quote"),
        _rule("ACCOUNT_IBAN_INVALID", name, not _iban_valid(f.value), NH,
              f"{f.value!r} fails the IBAN format or checksum", "IBAN checksum valid"),
        _single_value(name, f),
    ]


def _amount(ex: Extraction, text: str) -> list[RuleResult]:
    name, f = "amount", ex.amount
    in_letter = _eur_amounts(text)
    if not _present(f):
        if in_letter:
            return [_rule("AMOUNT_MISSED", name, True, NH,
                          f"model found none, but the letter contains EUR {sorted(map(str, in_letter))}", "")]
        return [_rule("AMOUNT_MISSING", name, True, REJECT, "no amount in the letter", "")]

    value = _dec(f.value)
    if value is None:
        return [*_common(name, f, text),
                _rule("AMOUNT_UNPARSEABLE", name, True, NH, f"{f.value!r} is not a number", "")]

    quote = f.source_quote or ""
    in_quote = _figures(quote)
    grounded = _in(quote, text) and value in in_quote
    others = {d for c in ex.amount.other_candidates if (d := _dec(c.value)) is not None}
    unexplained = in_letter - {value} - others
    is_restriction = ex.document_type is DocumentType.RESTRICTION
    reduces = any(o > value for o in others)
    return [
        *_common(name, f, text),
        _rule("AMOUNT_NOT_A_FIGURE", name, not in_quote, NH,
              f"amount is only described in words: {quote!r}", "stated as a figure"),
        _rule("AMOUNT_VALUE_NOT_IN_QUOTE", name, bool(in_quote) and value not in in_quote, NH,
              f"{f.value} is not the figure in {quote!r}", "value matches its quote"),
        _rule("AMOUNT_HEDGED", name, bool(_HEDGE.search(quote)), NH,
              f"amount is hedged: {quote!r}", "no hedging words"),
        _rule("AMOUNT_NOT_EUR", name, (f.currency or "").strip().upper() not in {"EUR", "€"}, NH,
              f"currency is {f.currency!r}, not EUR", "currency EUR"),
        # Reject only a non-positive amount that is really printed in the letter.
        _rule("AMOUNT_NOT_POSITIVE", name, value <= 0 and grounded, REJECT,
              f"amount {value} is not positive", "amount is positive"),
        _rule("AMOUNT_UNEXPLAINED_FIGURES", name, bool(unexplained), NH,
              f"the letter also cites EUR {sorted(map(str, unexplained))}, not accounted for",
              "every EUR figure in the letter is accounted for"),
        _rule("RESTRICTION_NOT_REDUCING", name, is_restriction and not reduces, NH,
              f"a restriction must lower an earlier amount, but {value} is not below any cited figure",
              "restriction lowers the earlier amount" if is_restriction else "not a restriction"),
    ]


def _document(ex: Extraction, text: str) -> list[RuleResult]:
    grounded = _in(ex.document_type_quote, text)
    return [
        _rule("DOCUMENT_TYPE_NOT_IN_LETTER", None, not grounded, NH,
              f"quote {ex.document_type_quote!r} does not appear in the letter", "document type quote found"),
        _rule("NOT_A_GARNISHMENT", None, ex.document_type is DocumentType.OTHER and grounded, REJECT,
              f"not a seizure order: {ex.document_type_quote!r}", f"document is a {ex.document_type}"),
    ]


def _confidence(f: ExtractedField, rules: list[RuleResult]) -> Confidence:
    fired = [r for r in rules if r.fired]
    if not _present(f):
        return Confidence.ABSENT
    if any(r.route is REJECT for r in fired):
        return Confidence.INVALID
    return Confidence.LOW if fired else Confidence.HIGH


def _verdict(document_rules: list[RuleResult], fields: dict[str, FieldEvidence]) -> Decision:
    every = document_rules + [r for f in fields.values() for r in f.rules]
    fired = sorted((r for r in every if r.fired), key=lambda r: -_SEVERITY[r.route])  # stable: keeps rule order
    return Decision(
        route=fired[0].route if fired else Route.AUTO,
        primary_rule=fired[0].rule if fired else "ALL_CHECKS_PASSED",
        reasons=[f"{r.rule}: {r.detail}" for r in fired] or ["all required fields present, exact and consistent"],
        fields=fields,
        document_rules=document_rules,
        rules_version=RULES_VERSION,
    )


def decide(text: str, ex: Extraction) -> Decision:
    checks = {
        "debtor_name": (ex.debtor_name, _debtor_name(ex.debtor_name, text)),
        "amount": (ex.amount, _amount(ex, text)),
        "case_reference": (ex.case_reference, _case_reference(ex.case_reference, text)),
        "account_iban": (ex.account_iban, _account_iban(ex.account_iban, text)),
    }
    fields = {
        name: FieldEvidence(value=f.value, source_quote=f.source_quote, status=f.status,
                            confidence=_confidence(f, rules), rules=rules)
        for name, (f, rules) in checks.items()
    }
    return _verdict(_document(ex, text), fields)


def extraction_failed(error: str) -> Decision:
    """No usable extraction (model down, refusal, invalid output): a human reads the letter."""
    rule = RuleResult(rule="EXTRACTION_FAILED", field=None, fired=True, route=NH, detail=error)
    return Decision(route=NH, primary_rule=rule.rule, reasons=[f"{rule.rule}: {error}"], fields={},
                    document_rules=[rule], rules_version=RULES_VERSION)
