"""The REST surface and the persisted record.

A fixed extractor stands in for the model so the HTTP and storage behaviour is exact; the real model is
exercised in test_samples_llm.py.
"""

import asyncio
from decimal import Decimal
from http import HTTPStatus
from typing import TYPE_CHECKING, override
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.usage import RunUsage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.decisions.llm_client import Extractor
from app.decisions.models import DecisionRow
from app.decisions.rules import decide
from app.main import create_app
from tests.test_rules import LETTER_1, ex1

if TYPE_CHECKING:
    from pathlib import Path

    from app.decisions.schema import Decision, Extraction


class FixedExtractor(Extractor):
    """Stands in for the model: returns a fixed extraction, or raises a fixed error."""

    model_name = "fixed-test-extractor"

    def __init__(self, result: Extraction | Exception) -> None:
        """Return or raise `result` on every call."""
        self.result = result

    @override
    async def extract(self, text: str, usage: RunUsage | None = None) -> Extraction:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class BilledExtractor(FixedExtractor):
    """Like FixedExtractor, but first spends 1,000 input and 500 output tokens on Claude Opus 5.5."""

    model_name = "anthropic:claude-opus-5-5"

    @override
    async def extract(self, text: str, usage: RunUsage | None = None) -> Extraction:
        assert usage is not None
        usage.incr(RunUsage(requests=1, input_tokens=1_000, output_tokens=500, cost=Decimal("0.014")))
        return await super().extract(text, usage)


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """Point each test at its own SQLite file."""
    return f"sqlite:///{tmp_path / 'test.db'}"


def client(result: Extraction | Exception, db_url: str) -> TestClient:
    """Build an app whose extractor returns or raises `result`."""
    return TestClient(create_app(FixedExtractor(result), db_url))


def test_post_returns_route_reasons_fields_and_confidence(db_url: str) -> None:
    """POST answers with the route, the reasons and each field's value and confidence."""
    r = client(ex1(), db_url).post("/decisions", json={"text": LETTER_1})
    assert r.status_code == HTTPStatus.CREATED
    body = r.json()
    assert (body["route"], body["primary_rule"]) == ("auto", "ALL_CHECKS_PASSED")
    assert body["fields"]["amount"]["value"] == "4250.00"
    assert body["fields"]["amount"]["confidence"] == "high"
    assert body["reasons"]


def test_get_returns_the_same_decision_with_its_evidence_from_disk(db_url: str) -> None:
    """GET returns exactly what POST stored, with the letter, the extraction and the versions."""
    posted = client(ex1(), db_url).post("/decisions", json={"text": LETTER_1}).json()
    # a fresh app on the same database file: the record really persisted
    got = client(ex1(), db_url).get(f"/decisions/{posted['id']}").json()
    assert got == posted
    assert got["letter_text"] == LETTER_1.strip()
    assert got["extraction"]["amount"]["source_quote"] == "Amount to seize: EUR 4,250.00"
    assert got["model"] == "fixed-test-extractor"
    assert got["prompt_version"]
    assert got["rules_version"]


def test_model_failure_is_recorded_as_needs_human(db_url: str) -> None:
    """A model error still stores the letter, routed to a person, with the error kept."""
    c = client(RuntimeError("model unavailable"), db_url)
    body = c.post("/decisions", json={"text": LETTER_1}).json()
    assert (body["route"], body["primary_rule"]) == ("needs_human", "EXTRACTION_FAILED")
    assert c.get(f"/decisions/{body['id']}").json()["error"] == "RuntimeError: model unavailable"


def test_rules_crash_is_loud_but_the_letter_is_kept(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A bug in the rules fails the request, but the letter is stored for a person first."""
    monkeypatch.setattr("app.decisions.service.decide", Mock(side_effect=ZeroDivisionError("bug in the rules")))
    app = create_app(FixedExtractor(ex1()), db_url)
    with pytest.raises(ZeroDivisionError):
        TestClient(app).post("/decisions", json={"text": LETTER_1})
    with Session(app.state.engine) as session:
        row = session.scalars(select(DecisionRow)).one()
    assert (row.route, row.primary_rule, row.letter_text) == ("needs_human", "RULES_FAILED", LETTER_1.strip())
    assert (row.usage, row.cost_usd) == (None, None)  # FixedExtractor makes no model call


def test_rules_run_off_the_event_loop(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A slow rule must not stall every other request, so the rules run in a worker thread, not on the loop."""
    on_loop: list[bool] = []

    def checked_decide(text: str, extraction: Extraction) -> Decision:
        try:
            asyncio.get_running_loop()
        except RuntimeError:  # raised only off the event loop
            on_loop.append(False)
        else:
            on_loop.append(True)
        return decide(text, extraction)

    monkeypatch.setattr("app.decisions.service.decide", checked_decide)
    assert client(ex1(), db_url).post("/decisions", json={"text": LETTER_1}).status_code == HTTPStatus.CREATED
    assert on_loop == [False]


@pytest.mark.parametrize("result", [ex1(), RuntimeError("model unavailable")], ids=["ok", "failed"])
def test_tokens_and_cost_are_stored_also_when_the_call_fails(result: Extraction | Exception, db_url: str) -> None:
    """Each decision keeps its model call's tokens and cost, also when the call failed: it was paid for."""
    app = create_app(BilledExtractor(result), db_url)
    posted = TestClient(app).post("/decisions", json={"text": LETTER_1}).json()
    with Session(app.state.engine) as session:
        row = session.scalars(select(DecisionRow)).one()
    assert row.usage is not None
    assert (row.usage["requests"], row.usage["input_tokens"], row.usage["output_tokens"]) == (1, 1_000, 500)
    assert row.cost_usd == Decimal("0.014")
    # the UI reads these from the API, the same before and after the round trip through the database
    got = TestClient(app).get(f"/decisions/{posted['id']}").json()
    assert (got["usage"]["input_tokens"], got["usage"]["output_tokens"], got["cost_usd"]) == (1_000, 500, 0.014)
    assert got == posted


@pytest.mark.parametrize("payload", [{"text": ""}, {"text": "   "}, {"text": "x" * 50_001}, {}])
def test_invalid_input_is_rejected(payload: dict[str, str], db_url: str) -> None:
    """Empty, blank, oversized or missing text is refused before any model call."""
    response = client(ex1(), db_url).post("/decisions", json=payload)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


def test_unknown_decision_is_404(db_url: str) -> None:
    """An unknown id is a 404."""
    assert client(ex1(), db_url).get("/decisions/nope").status_code == HTTPStatus.NOT_FOUND
