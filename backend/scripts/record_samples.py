"""Re-record the demo-mode readings through the app's own extractor: one live model call per letter in samples/.

Needs the model provider's key (ANTHROPIC_API_KEY for the default Haiku); costs under 1 cent with Haiku.
Writes PORTERS_RECORDINGS (default backend/recordings/samples.json). Run from backend/:

    uv run python -m scripts.record_samples
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic_ai.usage import RunUsage

from app.core.config import Settings
from app.decisions.llm_client import PROMPT_VERSION, LLMExtractor

SAMPLES = Path(__file__).parents[2] / "samples"


async def main() -> None:
    """Read every sample with the live model and write the readings, with each call's real tokens and cost."""
    settings = Settings.from_env()
    extractor = LLMExtractor(settings.llm_model)
    items = []
    for path in sorted(SAMPLES.glob("*.txt")):
        letter = path.read_text(encoding="utf-8").strip()  # the API strips the text before the model reads it
        usage = RunUsage()
        extraction = await extractor.extract(letter, usage)
        items.append(
            {
                "sample": path.name,
                "letter": letter,
                "extraction": extraction.model_dump(mode="json"),
                # not replayed (demo mode estimates its own); kept as the measured cost of a real reading
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cost_usd": None if usage.cost is None else float(usage.cost),
            }
        )
    recordings = {
        "model": settings.llm_model.split(":", 1)[-1],
        "source": f"{settings.llm_model} through LLMExtractor (scripts/record_samples.py), {datetime.now(UTC).date()}",
        "prompt_version": PROMPT_VERSION,
        "items": items,
    }
    text = json.dumps(recordings, indent=2, ensure_ascii=False) + "\n"
    settings.recordings_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
