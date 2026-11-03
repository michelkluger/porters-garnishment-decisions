"""Settings read from the environment, in one place."""

import os
from dataclasses import dataclass

DEFAULT_MODEL = "anthropic:claude-opus-5-5"


@dataclass(frozen=True)
class Settings:
    llm_model: str
    database_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            llm_model=os.environ.get("PORTERS_MODEL", DEFAULT_MODEL),
            database_url=os.environ.get("PORTERS_DB_URL", "sqlite:///porters.db"),
        )
