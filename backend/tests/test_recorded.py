"""Recorded real-model readings (Haiku, blind run over samples/) replayed through the rules: no key needed.

If a rule change breaks how a real model's reading is routed, this fails.
"""

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import RECORDINGS
from app.decisions.llm_client import RecordedExtractor
from app.decisions.rules import decide
from app.main import create_app

if TYPE_CHECKING:
    from pathlib import Path

ITEMS = json.loads(RECORDINGS.read_text(encoding="utf-8"))["items"]


@pytest.mark.parametrize("item", ITEMS, ids=[i["sample"] for i in ITEMS])
def test_recorded_reading_routes_as_labelled(item: dict[str, Any]) -> None:
    """Each recorded model reading still routes the way its sample is labelled."""
    extraction = asyncio.run(RecordedExtractor(RECORDINGS).extract(item["letter"]))
    expected = item["sample"].removesuffix(".txt").rsplit(".", 1)[1]
    assert decide(item["letter"], extraction).route == expected


def test_letter_matches_regardless_of_line_endings() -> None:
    """A letter uploaded with CRLF line endings finds its LF recording."""
    letter = ITEMS[0]["letter"]
    recorded = RecordedExtractor(RECORDINGS)
    assert asyncio.run(recorded.extract(letter.replace("\n", "\r\n") + "\r\n")) == asyncio.run(recorded.extract(letter))


def test_demo_mode_replays_known_letters_and_sends_unknown_ones_to_a_human(tmp_path: Path) -> None:
    """Without a key, recorded letters are decided and any other letter goes to a person."""
    c = TestClient(create_app(RecordedExtractor(RECORDINGS), f"sqlite:///{tmp_path / 'demo.db'}"))
    known = c.post("/decisions", json={"text": ITEMS[0]["letter"]}).json()
    assert known["model"] == "recorded:claude-haiku-5-5"
    assert known["primary_rule"] != "EXTRACTION_FAILED"
    # an estimate of what the live call would cost, so the UI has tokens and cost to show without a key
    assert known["usage"]["input_tokens"] > known["usage"]["output_tokens"] > 0
    assert 0 < known["cost_usd"] < 0.1  # noqa: PLR2004  a letter costs cents, not dollars
    unknown = c.post("/decisions", json={"text": "A letter nobody recorded."}).json()
    assert (unknown["route"], unknown["primary_rule"]) == ("needs_human", "EXTRACTION_FAILED")
    assert "set ANTHROPIC_API_KEY" in unknown["error"]
    assert (unknown["usage"], unknown["cost_usd"]) == (None, None)
