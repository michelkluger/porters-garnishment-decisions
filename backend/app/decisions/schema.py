"""Pydantic schemas: the LLM output contract, the decision the rules produce, and the API contract."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# --- what the LLM returns ---------------------------------------------------------------------------


class Status(StrEnum):
    EXPLICIT = "explicit"
    APPROXIMATE = "approximate"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    ABSENT = "absent"


class DocumentType(StrEnum):
    ORDER = "garnishment_order"
    RESTRICTION = "garnishment_restriction"
    OTHER = "not_a_garnishment"


class Candidate(BaseModel):
    value: str
    source_quote: str
    role: str = Field(description="Why this is not the operative value.")


class ExtractedField(BaseModel):
    value: str | None
    source_quote: str | None = Field(description="Exact span copied from the letter, or null if absent.")
    status: Status
    other_candidates: list[Candidate]


class AmountField(ExtractedField):
    currency: str | None = Field(description="ISO currency code, e.g. EUR.")


class Extraction(BaseModel):
    document_type: DocumentType
    document_type_quote: str = Field(description="Exact words in the letter that show its type.")
    debtor_name: ExtractedField
    amount: AmountField
    case_reference: ExtractedField
    account_iban: ExtractedField


# --- what the rules decide ----------------------------------------------------------------------------


class Route(StrEnum):
    AUTO = "auto"
    NEEDS_HUMAN = "needs_human"
    REJECT = "reject"


class Confidence(StrEnum):
    HIGH = "high"  # present and every rule on it passed
    LOW = "low"  # present but a rule sent it to a human
    INVALID = "invalid"  # a hard validation failed
    ABSENT = "absent"


class RuleResult(BaseModel):
    rule: str
    field: str | None
    fired: bool
    route: Route  # the route this rule forces when it fires
    detail: str


class FieldEvidence(BaseModel):
    value: str | None
    source_quote: str | None
    status: Status
    confidence: Confidence
    rules: list[RuleResult]


class Decision(BaseModel):
    route: Route
    primary_rule: str
    reasons: list[str]
    fields: dict[str, FieldEvidence]
    document_rules: list[RuleResult]
    rules_version: str


# --- the REST API ----------------------------------------------------------------------------------------

LetterText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50_000)]


class DecisionRequest(BaseModel):
    text: LetterText


class DecisionResponse(Decision):
    id: str
    created_at: datetime
    letter_text: str
    extraction: Extraction | None
    model: str
    prompt_version: str
    error: str | None
