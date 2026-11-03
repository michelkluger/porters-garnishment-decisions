"""App factory: builds the shared infrastructure once and mounts the routers.

Run with `uvicorn app.main:create_app --factory`.
"""

import logging

from fastapi import FastAPI

from app.core.config import Settings
from app.core.database import create_db_engine
from app.decisions import models  # noqa: F401  registers the tables before create_all
from app.decisions.llm_client import Extractor, LLMExtractor, RecordedExtractor
from app.decisions.router import router as decisions_router

log = logging.getLogger(__name__)


def _default_extractor(settings: Settings) -> Extractor:
    if settings.extractor == "recorded":
        log.warning("No API key: replaying recorded extractions from %s (demo mode)", settings.recordings_path)
        return RecordedExtractor(settings.recordings_path)
    return LLMExtractor(settings.llm_model)


def create_app(extractor: Extractor | None = None, db_url: str | None = None) -> FastAPI:
    """Build the app; tests pass their own extractor and database."""
    settings = Settings.from_env()
    app = FastAPI(title="Porters garnishment decisions")
    app.state.engine = create_db_engine(db_url or settings.database_url)
    app.state.extractor = extractor or _default_extractor(settings)
    app.include_router(decisions_router)
    return app
