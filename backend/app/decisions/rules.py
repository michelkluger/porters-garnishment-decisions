"""Deterministic routing: (letter text, extraction) -> decision.

Pure functions only: no I/O, no clock, no randomness, so the same input always gives the same route.
Every rule is evaluated and recorded, fired or not; the route is the most severe one that fired.
"""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from .schema import (
    Confidence,
    Decision,
    DocumentType,
    ExtractedField,
    Extraction,
    FieldEvidence,
    Route,
    RuleResult,
    Status,
)

RULES_VERSION = "3"

NH, REJECT = Route.NEEDS_HUMAN, Route.REJECT
_SEVERITY = {Route.AUTO: 0, Route.NEEDS_HUMAN: 1, Route.REJECT: 2}
_UNCERTAIN = {Status.APPROXIMATE, Status.PARTIAL, Status.AMBIGUOUS}

# shortcut: English number format only ("4,250.00"); "4.250,00" fails the value-vs-quote check
# and goes to a human. Upgrade when letters arrive in other locales.
_FIGURE = r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
# the lookbehind stops a suffix figure starting mid-number, which made long digit runs backtrack quadratically
_EUR_AMOUNT = re.compile(rf"(?:EUR|€)[\s:)]*({_FIGURE})|(?<![\d,.])({_FIGURE})\s*(?:€|(?:EUR|euros?)\b)", re.IGNORECASE)
_HEDGE = re.compile(
    r"\b(?:approx\w*|about|around|circa|roughly|estimated|in the region of|or so)\b|\bca\.", re.IGNORECASE
)
_CASE_REF = re.compile(r"[A-Z]{2}-\d+/\d+")  # spec: two letters, digits, slash, digits
_INITIAL = re.compile(r"(?:[^\W\d_]\.)*[^\W\d_]\.?")  # "J", "J." or "J.A."
_TITLE = re.compile(r"^(?:(?:mr|mrs|ms|miss|dr|prof|herr|frau)\.?\s+)+", re.IGNORECASE)  # "Herr Dr. ", not "Alexandr "
_FULL_NAME_WORDS = 2  # a first name and a surname


def _norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", s).split())


def _in(fragment: str | None, text: str) -> bool:
    """Is the fragment in the text, ignoring spacing (not case). Used to check that a quote is really in the letter."""
    fragment = _norm(fragment or "")
    return bool(fragment) and fragment in _norm(text)


def _quote_lines(quote: str, text: str) -> str:
    """Return the whole letter line(s) the quote sits on, or the quote itself if it is not in the letter."""
    text = unicodedata.normalize("NFKC", text) + "\n"
    words = _norm(quote).split()
    hits = re.finditer(r"\s+".join(map(re.escape, words)), text) if words else ()
    return "\n".join(text[text.rfind("\n", 0, m.start()) + 1 : text.find("\n", m.end())] for m in hits) or quote


def _verbatim(value: str | None, text: str | None) -> bool:
    """Is the value in the text exactly as written and whole: "AB-1042/2" is not in "AB-1042/24"."""
    value = _norm(value or "")
    return bool(value) and re.search(rf"(?<![\w/-]){re.escape(value)}(?![\w/-])", _norm(text or "")) is not None


def _dec(s: str) -> Decimal | None:
    try:
        d = Decimal(s.replace(",", "").strip())
    except InvalidOperation:
        return None
    return d if d.is_finite() else None  # "NaN" and "Infinity" parse, but crash comparisons


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


def _rule(rule: str, field: str | None, route: Route, *, fired: bool, detail: tuple[str, str]) -> RuleResult:
    """Record one rule; `detail` is (the text if it fired, the text if it did not)."""
    return RuleResult(rule=rule, field=field, fired=fired, route=route, detail=detail[0] if fired else detail[1])


def _present(f: ExtractedField) -> str | None:
    """Return the field's value, or None if the model found nothing usable."""
    return f.value if f.status is not Status.ABSENT and f.value and f.value.strip() else None


def _common(name: str, f: ExtractedField, text: str) -> list[RuleResult]:
    """Rules every present field must pass: its quote is really in the letter and the model was sure."""
    tag = name.upper()
    return [
        _rule(
            f"{tag}_NOT_IN_LETTER",
            name,
            NH,
            fired=not _in(f.source_quote, text),
            detail=(f"quote {f.source_quote!r} does not appear in the letter", "quote found in the letter"),
        ),
        _rule(
            f"{tag}_UNCERTAIN",
            name,
            NH,
            fired=f.status in _UNCERTAIN,
            detail=(f"model marked it {f.status}", "model marked it explicit"),
        ),
    ]


def _single_value(name: str, f: ExtractedField) -> RuleResult:
    """Name, case reference and IBAN have exactly one right answer; any rival means ambiguity."""
    rivals = [c.value for c in f.other_candidates]
    return _rule(
        f"{name.upper()}_HAS_ALTERNATIVES",
        name,
        NH,
        fired=bool(rivals),
        detail=(f"other possible values in the letter: {rivals}", "no other possible values"),
    )


def _debtor_name(f: ExtractedField, text: str) -> list[RuleResult]:
    name = "debtor_name"
    if (value := _present(f)) is None:
        # OPEN: the spec lists no-amount and bad case reference as rejects, not a missing name.
        # Sent to a human until that is agreed.
        return [_rule("DEBTOR_NAME_MISSING", name, NH, fired=True, detail=("no debtor name in the letter", ""))]
    tokens = _TITLE.sub("", value.strip()).split()  # "Mr. Meyer" has no first name
    # a middle initial is fine ("Jordan A. Meyer"); an initial for the first name or surname is not
    partial = len(tokens) < _FULL_NAME_WORDS or any(_INITIAL.fullmatch(t) for t in (tokens[0], tokens[-1]))
    return [
        *_common(name, f, text),
        _rule(
            "DEBTOR_NAME_VALUE_NOT_IN_QUOTE",
            name,
            NH,
            fired=not _verbatim(value, f.source_quote),
            detail=(f"{value!r} is not what the quote says", "value matches its quote"),
        ),
        _rule(
            "DEBTOR_NAME_PARTIAL",
            name,
            NH,
            fired=partial,
            detail=(f"{value!r} is not a full name (single word, initial or title only)", "full name"),
        ),
        _single_value(name, f),
    ]


def _case_reference(f: ExtractedField, text: str) -> list[RuleResult]:
    name = "case_reference"
    if (value := _present(f)) is None:
        in_text = _CASE_REF.findall(text)
        if in_text:
            missed = f"model found none, but the letter contains {in_text}"
            return [_rule("CASE_REFERENCE_MISSED", name, NH, fired=True, detail=(missed, ""))]
        return [
            _rule("CASE_REFERENCE_MISSING", name, REJECT, fired=True, detail=("no case reference in the letter", ""))
        ]
    malformed = not _CASE_REF.fullmatch(value.strip())
    return [
        *_common(name, f, text),
        _rule(
            "CASE_REFERENCE_VALUE_NOT_IN_QUOTE",
            name,
            NH,
            fired=not _verbatim(value, f.source_quote),
            detail=(f"{value!r} is not what the quote says", "value matches its quote"),
        ),
        # Reject only when the malformed value is printed in the letter exactly as given, not a misread.
        _rule(
            "CASE_REFERENCE_MALFORMED",
            name,
            REJECT,
            fired=malformed and _verbatim(value, text),
            detail=(f"{value!r} is not in the format XX-0000/00", "format XX-0000/00"),
        ),
        _single_value(name, f),
    ]


def _account_iban(f: ExtractedField, text: str) -> list[RuleResult]:
    name = "account_iban"
    if (value := _present(f)) is None:
        # OPEN: the spec only says a missing IBAN must not force a reject. Without it the bank must
        # match the debtor to an account by name, so it goes to a human until agreed otherwise.
        return [_rule("ACCOUNT_IBAN_MISSING", name, NH, fired=True, detail=("no IBAN in the letter", ""))]
    return [
        *_common(name, f, text),
        _rule(
            "ACCOUNT_IBAN_VALUE_NOT_IN_QUOTE",
            name,
            NH,
            fired=_compact(value) not in _compact(f.source_quote or ""),
            detail=(f"{value!r} is not what the quote says", "value matches its quote"),
        ),
        _rule(
            "ACCOUNT_IBAN_INVALID",
            name,
            NH,
            fired=not _iban_valid(value),
            detail=(f"{value!r} fails the IBAN format or checksum", "IBAN checksum valid"),
        ),
        _single_value(name, f),
    ]


def _amount(ex: Extraction, text: str) -> list[RuleResult]:
    name, f = "amount", ex.amount
    in_letter = _eur_amounts(text)
    shown = sorted(map(str, in_letter))
    if (raw := _present(f)) is None:
        if in_letter:
            missed = f"model found none, but the letter contains EUR {shown}"
            return [_rule("AMOUNT_MISSED", name, NH, fired=True, detail=(missed, ""))]
        return [_rule("AMOUNT_MISSING", name, REJECT, fired=True, detail=("no amount in the letter", ""))]

    value = _dec(raw)
    if value is None:
        return [
            *_common(name, f, text),
            _rule("AMOUNT_UNPARSEABLE", name, NH, fired=True, detail=(f"{raw!r} is not a number", "")),
        ]

    quote = f.source_quote or ""
    # the prompt asks for the shortest quote, which drops a hedge just before the figure ("approximately EUR 3,000")
    quote_lines = _quote_lines(quote, text)
    in_quote = _figures(quote)
    grounded = _in(quote, text) and value in in_quote
    # only rivals printed in the letter count: an invented higher figure must not make a restriction look reducing
    others = {d for c in ex.amount.other_candidates if (d := _dec(c.value)) is not None} & in_letter
    unexplained = in_letter - {value} - others
    eur = (f.currency or "").strip().upper() in {"EUR", "€"} and value in in_letter
    is_restriction = ex.document_type is DocumentType.RESTRICTION
    reduces = any(o > value for o in others)
    return [
        *_common(name, f, text),
        _rule(
            "AMOUNT_NOT_A_FIGURE",
            name,
            NH,
            fired=not in_quote,
            detail=(f"amount is only described in words: {quote!r}", "stated as a figure"),
        ),
        _rule(
            "AMOUNT_VALUE_NOT_IN_QUOTE",
            name,
            NH,
            fired=bool(in_quote) and value not in in_quote,
            detail=(f"{raw} is not the figure in {quote!r}", "value matches its quote"),
        ),
        _rule(
            "AMOUNT_HEDGED",
            name,
            NH,
            fired=bool(_HEDGE.search(quote_lines)),
            detail=(f"amount is hedged: {quote_lines!r}", "no hedging words"),
        ),
        # the figure must also be printed as EUR in the letter, whatever currency the model reports
        _rule(
            "AMOUNT_NOT_EUR",
            name,
            NH,
            fired=not eur,
            detail=(
                f"not shown as EUR: model said {f.currency!r}, the letter's EUR figures are {shown}",
                "currency EUR, printed as EUR in the letter",
            ),
        ),
        # Reject only a non-positive amount that is really printed in the letter.
        _rule(
            "AMOUNT_NOT_POSITIVE",
            name,
            REJECT,
            fired=value <= 0 and grounded,
            detail=(f"amount {value} is not positive", "amount is positive"),
        ),
        _rule(
            "AMOUNT_UNEXPLAINED_FIGURES",
            name,
            NH,
            fired=bool(unexplained),
            detail=(
                f"the letter also cites EUR {sorted(map(str, unexplained))}, not accounted for",
                "every EUR figure in the letter is accounted for",
            ),
        ),
        # only a restriction has a rule for which cited figure applies; anywhere else the choice is unchecked
        _rule(
            "AMOUNT_HAS_ALTERNATIVES",
            name,
            NH,
            fired=not is_restriction and bool(others),
            detail=(
                f"the letter also cites EUR {sorted(map(str, others))} as rival amounts",
                "restriction: checked by RESTRICTION_NOT_REDUCING" if is_restriction else "no rival EUR figures",
            ),
        ),
        _rule(
            "RESTRICTION_NOT_REDUCING",
            name,
            NH,
            fired=is_restriction and not reduces,
            detail=(
                f"a restriction must lower an earlier amount, but {value} is not below any cited figure",
                "restriction lowers the earlier amount" if is_restriction else "not a restriction",
            ),
        ),
    ]


def _document(ex: Extraction, text: str) -> list[RuleResult]:
    grounded = _in(ex.document_type_quote, text)
    other = ex.document_type is DocumentType.OTHER and grounded
    # The type is the model's judgement, so it alone must not reject a letter that names an EUR sum.
    eur = sorted(map(str, _eur_amounts(text)))
    return [
        _rule(
            "DOCUMENT_TYPE_NOT_IN_LETTER",
            None,
            NH,
            fired=not grounded,
            detail=(f"quote {ex.document_type_quote!r} does not appear in the letter", "document type quote found"),
        ),
        _rule(
            "NOT_A_GARNISHMENT",
            None,
            REJECT,
            fired=other and not eur,
            detail=(f"not a seizure order: {ex.document_type_quote!r}", f"document is a {ex.document_type}"),
        ),
        _rule(
            "NOT_A_GARNISHMENT_UNCONFIRMED",
            None,
            NH,
            fired=other and bool(eur),
            detail=(
                f"model says not a seizure order, but the letter cites EUR {eur}",
                "no conflict between document type and letter",
            ),
        ),
    ]


def _confidence(f: ExtractedField, rules: list[RuleResult]) -> Confidence:
    fired = [r for r in rules if r.fired]
    if _present(f) is None:
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
    """Route a letter from what the model read in it. Same input, same decision."""
    checks = {
        "debtor_name": (ex.debtor_name, _debtor_name(ex.debtor_name, text)),
        "amount": (ex.amount, _amount(ex, text)),
        "case_reference": (ex.case_reference, _case_reference(ex.case_reference, text)),
        "account_iban": (ex.account_iban, _account_iban(ex.account_iban, text)),
    }
    fields = {
        name: FieldEvidence(
            value=f.value, source_quote=f.source_quote, status=f.status, confidence=_confidence(f, rules), rules=rules
        )
        for name, (f, rules) in checks.items()
    }
    return _verdict(_document(ex, text), fields)


def extraction_failed(error: str, rule: str = "EXTRACTION_FAILED") -> Decision:
    """No usable extraction (model down, refusal, invalid output) or a crash in the rules: a human reads the letter."""
    result = RuleResult(rule=rule, field=None, fired=True, route=NH, detail=error)
    return Decision(
        route=NH,
        primary_rule=rule,
        reasons=[f"{rule}: {error}"],
        fields={},
        document_rules=[result],
        rules_version=RULES_VERSION,
    )
