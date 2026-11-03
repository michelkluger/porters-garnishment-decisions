"""ORM table: the append-only decision log. Rows are written once and never updated."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DecisionRow(Base):
    """One decision: the letter, what the model read, what the rules decided and why."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(primary_key=True)
    created_at: Mapped[datetime]
    route: Mapped[str] = mapped_column(index=True)
    primary_rule: Mapped[str]
    case_reference: Mapped[str | None] = mapped_column(index=True)
    letter_text: Mapped[str] = mapped_column(Text)
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # model output exactly as received
    decision: Mapped[dict[str, Any]] = mapped_column(JSON)  # per-field confidence, every rule, reasons
    model: Mapped[str]
    prompt_version: Mapped[str]
    rules_version: Mapped[str]
    error: Mapped[str | None]
