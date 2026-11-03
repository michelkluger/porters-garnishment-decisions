"""Use cases: extract, decide, record. No HTTP and no SQL here; those live in the router and repository."""

import logging
import uuid
from datetime import UTC, datetime

from .llm_client import PROMPT_VERSION, Extractor
from .models import DecisionRow
from .repository import DecisionRepository
from .rules import decide, extraction_failed
from .schema import DecisionResponse

log = logging.getLogger(__name__)


class DecisionService:
    def __init__(self, extractor: Extractor, repository: DecisionRepository):
        self._extractor = extractor
        self._repository = repository

    async def create(self, text: str) -> DecisionResponse:
        extraction, error, crash = None, None, None
        try:
            extraction = await self._extractor.extract(text)
        except Exception as e:  # model down, refusal, bad output: never lose the letter, a human reads it
            log.exception("extraction failed")
            error = f"{type(e).__name__}: {e}"
            decision = extraction_failed(error)
        else:
            try:
                decision = decide(text, extraction)
            except Exception as e:  # a rules bug: keep the letter on record for a human, then stay loud (500)
                crash, error = e, f"{type(e).__name__}: {e}"
                decision = extraction_failed(error, rule="RULES_FAILED")
        # OPEN: a repeated letter is not detected and gets a second decision (NOTES.md, open decision 7).
        row = self._repository.add(DecisionRow(
            id=str(uuid.uuid4()), created_at=datetime.now(UTC), route=decision.route,
            primary_rule=decision.primary_rule,
            case_reference=extraction.case_reference.value if extraction else None,
            letter_text=text, extraction=extraction.model_dump(mode="json") if extraction else None,
            decision=decision.model_dump(mode="json"), model=self._extractor.model_name,
            prompt_version=PROMPT_VERSION, rules_version=decision.rules_version, error=error,
        ))
        if crash:
            raise crash
        return _to_response(row)

    def get(self, decision_id: str) -> DecisionResponse | None:
        row = self._repository.get(decision_id)
        return _to_response(row) if row else None


def _to_response(row: DecisionRow) -> DecisionResponse:
    return DecisionResponse(
        **row.decision, id=row.id, letter_text=row.letter_text,
        created_at=row.created_at.replace(tzinfo=UTC),  # stored as UTC; SQLite drops the tzinfo
        extraction=row.extraction, model=row.model, prompt_version=row.prompt_version, error=row.error,
    )
