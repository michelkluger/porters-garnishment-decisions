"""Real model + real rules over every labelled letter in samples/ (label = the part before .txt).

Costs money and needs credentials, so it only runs when asked: PORTERS_LLM_TESTS=1 uv run pytest
"""

import asyncio
import os
from pathlib import Path

import pytest

from app.core.config import Settings
from app.decisions.llm_client import LLMExtractor
from app.decisions.rules import decide

SAMPLES = sorted((Path(__file__).parents[2] / "samples").glob("*.txt"))

pytestmark = pytest.mark.skipif(os.environ.get("PORTERS_LLM_TESTS") != "1", reason="set PORTERS_LLM_TESTS=1")


@pytest.mark.parametrize("path", SAMPLES, ids=[p.stem for p in SAMPLES])
def test_sample_routes_as_labelled(path):
    text = path.read_text(encoding="utf-8")
    extraction = asyncio.run(LLMExtractor(Settings.from_env().llm_model).extract(text))
    decision = decide(text, extraction)
    assert decision.route == path.stem.rsplit(".", 1)[1], decision.reasons
