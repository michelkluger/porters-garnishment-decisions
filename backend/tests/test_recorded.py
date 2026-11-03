"""Recorded real-model readings (Haiku, blind run over samples/) replayed through the rules: no key needed.

If a rule change breaks how a real model's reading is routed, this fails.
"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import RECORDINGS
from app.decisions.llm_client import RecordedExtractor
from app.decisions.rules import decide
from app.main import create_app

ITEMS = json.loads(RECORDINGS.read_text(encoding="utf-8"))["items"]


@pytest.mark.parametrize("item", ITEMS, ids=[i["sample"] for i in ITEMS])
def test_recorded_reading_routes_as_labelled(item):
    extraction = asyncio.run(RecordedExtractor(RECORDINGS).extract(item["letter"]))
    expected = item["sample"].removesuffix(".txt").rsplit(".", 1)[1]
    assert decide(item["letter"], extraction).route == expected


def test_letter_matches_regardless_of_line_endings():
    letter = ITEMS[0]["letter"]
    recorded = RecordedExtractor(RECORDINGS)
    assert asyncio.run(recorded.extract(letter.replace("\n", "\r\n") + "\r\n")) == asyncio.run(recorded.extract(letter))


def test_demo_mode_replays_known_letters_and_sends_unknown_ones_to_a_human(tmp_path):
    c = TestClient(create_app(RecordedExtractor(RECORDINGS), f"sqlite:///{tmp_path / 'demo.db'}"))
    known = c.post("/decisions", json={"text": ITEMS[0]["letter"]}).json()
    assert known["model"] == "recorded:claude-haiku" and known["primary_rule"] != "EXTRACTION_FAILED"
    unknown = c.post("/decisions", json={"text": "A letter nobody recorded."}).json()
    assert (unknown["route"], unknown["primary_rule"]) == ("needs_human", "EXTRACTION_FAILED")
    assert "set ANTHROPIC_API_KEY" in unknown["error"]
