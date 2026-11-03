"""The REST surface and the persisted record. A fixed extractor stands in for the model so the HTTP and
storage behaviour is exact; the real model is exercised in test_samples_llm.py."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.decisions.models import DecisionRow
from app.main import create_app
from test_rules import LETTER_1, ex1


class FixedExtractor:
    model_name = "fixed-test-extractor"

    def __init__(self, result):
        self.result = result

    async def extract(self, text):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{tmp_path / 'test.db'}"


def client(result, db_url):
    return TestClient(create_app(FixedExtractor(result), db_url))


def test_post_returns_route_reasons_fields_and_confidence(db_url):
    r = client(ex1(), db_url).post("/decisions", json={"text": LETTER_1})
    assert r.status_code == 201
    body = r.json()
    assert (body["route"], body["primary_rule"]) == ("auto", "ALL_CHECKS_PASSED")
    assert body["fields"]["amount"]["value"] == "4250.00"
    assert body["fields"]["amount"]["confidence"] == "high"
    assert body["reasons"]


def test_get_returns_the_same_decision_with_its_evidence_from_disk(db_url):
    posted = client(ex1(), db_url).post("/decisions", json={"text": LETTER_1}).json()
    # a fresh app on the same database file: the record really persisted
    got = client(ex1(), db_url).get(f"/decisions/{posted['id']}").json()
    assert got == posted
    assert got["letter_text"] == LETTER_1.strip()
    assert got["extraction"]["amount"]["source_quote"] == "Amount to seize: EUR 4,250.00"
    assert got["model"] == "fixed-test-extractor" and got["prompt_version"] and got["rules_version"]


def test_model_failure_is_recorded_as_needs_human(db_url):
    c = client(RuntimeError("model unavailable"), db_url)
    body = c.post("/decisions", json={"text": LETTER_1}).json()
    assert (body["route"], body["primary_rule"]) == ("needs_human", "EXTRACTION_FAILED")
    assert c.get(f"/decisions/{body['id']}").json()["error"] == "RuntimeError: model unavailable"


def test_rules_crash_is_loud_but_the_letter_is_kept(db_url, monkeypatch):
    def broken_rules(text, extraction):
        raise ZeroDivisionError("bug in the rules")

    monkeypatch.setattr("app.decisions.service.decide", broken_rules)
    app = create_app(FixedExtractor(ex1()), db_url)
    with pytest.raises(ZeroDivisionError):
        TestClient(app).post("/decisions", json={"text": LETTER_1})
    with Session(app.state.engine) as session:
        row = session.scalars(select(DecisionRow)).one()
    assert (row.route, row.primary_rule, row.letter_text) == ("needs_human", "RULES_FAILED", LETTER_1.strip())


@pytest.mark.parametrize("payload",[{"text": ""}, {"text": "   "}, {"text": "x" * 50_001}, {}])
def test_invalid_input_is_rejected(payload, db_url):
    assert client(ex1(), db_url).post("/decisions", json=payload).status_code == 422


def test_unknown_decision_is_404(db_url):
    assert client(ex1(), db_url).get("/decisions/nope").status_code == 404
