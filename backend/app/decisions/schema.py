"""Pydantic schemas: the LLM output contract, the decision the rules produce, and the API contract."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

# --- what the LLM returns ---------------------------------------------------------------------------
# OPEN: no class docstrings here (noqa: D101). Pydantic sends them to the model as schema descriptions, so
# one would change the prompt; add them only together with a PROMPT_VERSION bump and a run of test_samples_llm.


class Status(StrEnum):  # noqa: D101
    EXPLICIT = "explicit"
    APPROXIMATE = "approximate"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    ABSENT = "absent"


class DocumentType(StrEnum):  # noqa: D101
    ORDER = "garnishment_order"
    RESTRICTION = "garnishment_restriction"
    OTHER = "not_a_garnishment"


class Candidate(BaseModel):  # noqa: D101
    value: str
    source_quote: str
    role: str = Field(description="Why this is not the operative value.")


class ExtractedField(BaseModel):  # noqa: D101
    value: str | None
    source_quote: str | None = Field(description="Exact span copied from the letter, or null if absent.")
    status: Status
    other_candidates: list[Candidate]


class AmountField(ExtractedField):  # noqa: D101
    currency: str | None = Field(description="ISO currency code, e.g. EUR.")


class Extraction(BaseModel):  # noqa: D101
    document_type: DocumentType
    document_type_quote: str = Field(description="Exact words in the letter that show its type.")
    debtor_name: ExtractedField
    amount: AmountField
    case_reference: ExtractedField
    account_iban: ExtractedField


# --- what the rules decide ----------------------------------------------------------------------------


class Route(StrEnum):
    """Where a letter goes: processed automatically, to a person, or refused."""

    AUTO = "auto"
    NEEDS_HUMAN = "needs_human"
    REJECT = "reject"


class Confidence(StrEnum):
    """How far a field can be trusted after the rules ran."""

    HIGH = "high"  # present and every rule on it passed
    LOW = "low"  # present but a rule sent it to a human
    INVALID = "invalid"  # a hard validation failed
    ABSENT = "absent"


class RuleResult(BaseModel):
    """One rule's outcome, recorded whether it fired or not."""

    rule: str
    field: str | None
    fired: bool
    route: Route  # the route this rule forces when it fires
    detail: str


class FieldEvidence(BaseModel):
    """A field's value and quote, and every rule that checked it."""

    value: str | None
    source_quote: str | None
    status: Status
    confidence: Confidence
    rules: list[RuleResult]


class Decision(BaseModel):
    """The route, the rule that set it, and all the evidence behind it."""

    route: Route
    primary_rule: str
    reasons: list[str]
    fields: dict[str, FieldEvidence]
    document_rules: list[RuleResult]
    rules_version: str


# --- the REST API ----------------------------------------------------------------------------------------

LetterText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50_000)]


class DecisionRequest(BaseModel):
    """A court letter to decide on."""

    text: LetterText


class DecisionResponse(Decision):
    """A recorded decision: the decision plus the letter, the model reading and the versions used."""

    id: str
    created_at: datetime
    letter_text: str
    extraction: Extraction | None
    model: str
    usage: dict[str, Any] | None
    cost_usd: float | None  # float, not Decimal: same JSON before and after the DB round trip ("0.014" vs "0.014000")
    prompt_version: str
    error: str | None
