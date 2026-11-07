"""Use cases: extract, decide, record. No HTTP and no SQL here; those live in the router and repository."""

import asyncio
import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic_ai.usage import RunUsage

from .llm_client import PROMPT_VERSION, Extractor, NotRecordedError
from .models import DecisionRow
from .rules import decide, extraction_failed
from .schema import Decision, DecisionResponse, Extraction

if TYPE_CHECKING:
    from .repository import DecisionRepository

log = logging.getLogger(__name__)


class DecisionService:
    """Turns a letter into a recorded decision, and reads recorded decisions back."""

    def __init__(self, extractor: Extractor, repository: DecisionRepository) -> None:
        """Use this extractor to read letters and this repository to record decisions."""
        self._extractor = extractor
        self._repository = repository

    async def create(self, text: str) -> DecisionResponse:
        """Extract, decide and record. Every letter is recorded, even when the model or the rules fail."""
        usage = RunUsage()  # failed calls are paid for too, so usage is recorded on every path
        try:
            extraction = await self._extractor.extract(text, usage)
        except Exception as e:  # model down, refusal, bad output: never lose the letter, a human reads it
            log.exception("extraction failed")
            # a provider's message can carry its raw response or request metadata: callers get the class, the log all
            error = f"{type(e).__name__}: {e}" if isinstance(e, NotRecordedError) else type(e).__name__
            return await asyncio.to_thread(self._record, text, usage, None, extraction_failed(error), error)
        # the rules and the SQLite commit are sync: run them off the event loop so one slow letter blocks no one else
        return await asyncio.to_thread(self._decide_and_record, text, usage, extraction)

    def _decide_and_record(self, text: str, usage: RunUsage, extraction: Extraction) -> DecisionResponse:
        try:
            decision = decide(text, extraction)
        except Exception as e:  # a rules bug: keep the letter on record for a human, then stay loud (500)
            error = f"{type(e).__name__}: {e}"
            self._record(text, usage, extraction, extraction_failed(error, rule="RULES_FAILED"), error)
            raise
        return self._record(text, usage, extraction, decision, None)

    def get(self, decision_id: str) -> DecisionResponse | None:
        """Return a recorded decision, or None if there is none with this id."""
        row = self._repository.get(decision_id)
        return _to_response(row) if row else None

    def _record(
        self, text: str, usage: RunUsage, extraction: Extraction | None, decision: Decision, error: str | None
    ) -> DecisionResponse:
        # OPEN: a repeated letter is not detected and gets a second decision (NOTES.md, open decision 7).
        row = self._repository.add(
            DecisionRow(
                id=str(uuid.uuid4()),
                created_at=datetime.now(UTC),
                route=decision.route,
                primary_rule=decision.primary_rule,
                case_reference=extraction.case_reference.value if extraction else None,
                letter_text=text,
                extraction=extraction.model_dump(mode="json") if extraction else None,
                decision=decision.model_dump(mode="json"),
                model=self._extractor.model_name,
                # cost has its own column; the raw counts stay so the cost can be checked later
                usage={k: v for k, v in asdict(usage).items() if k != "cost"} if usage.requests else None,
                cost_usd=usage.cost,
                prompt_version=PROMPT_VERSION,
                rules_version=decision.rules_version,
                error=error,
            )
        )
        return _to_response(row)


def _to_response(row: DecisionRow) -> DecisionResponse:
    return DecisionResponse(
        **row.decision,
        id=row.id,
        letter_text=row.letter_text,
        created_at=row.created_at.replace(tzinfo=UTC),  # stored as UTC; SQLite drops the tzinfo
        extraction=row.extraction,
        model=row.model,
        usage=row.usage,
        cost_usd=row.cost_usd,
        prompt_version=row.prompt_version,
        error=row.error,
    )
