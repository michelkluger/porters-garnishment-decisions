"""Settings read from the environment, in one place."""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "anthropic:claude-opus-5-5"
RECORDINGS = Path(__file__).parents[2] / "recordings" / "haiku-subagent.json"


@dataclass(frozen=True)
class Settings:
    llm_model: str
    database_url: str
    extractor: str  # "llm" (live model calls) or "recorded" (replay recorded extractions)
    recordings_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        # shortcut: only the Anthropic key is checked; set PORTERS_EXTRACTOR=llm when using another provider.
        default_extractor = "llm" if os.environ.get("ANTHROPIC_API_KEY") else "recorded"
        return cls(
            llm_model=os.environ.get("PORTERS_MODEL", DEFAULT_MODEL),
            database_url=os.environ.get("PORTERS_DB_URL", "sqlite:///porters.db"),
            extractor=os.environ.get("PORTERS_EXTRACTOR", default_extractor),
            recordings_path=Path(os.environ.get("PORTERS_RECORDINGS", RECORDINGS)),
        )
