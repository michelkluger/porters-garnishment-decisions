"""Wires a DecisionService per request from the app's extractor and a fresh DB session."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session  # noqa: TC002  FastAPI reads this annotation at runtime to resolve Depends

from app.core.database import get_session

from .repository import DecisionRepository
from .service import DecisionService


def get_decision_service(request: Request, session: Annotated[Session, Depends(get_session)]) -> DecisionService:
    """FastAPI dependency: a service bound to this request's session."""
    return DecisionService(request.app.state.extractor, DecisionRepository(session))


DecisionServiceDep = Annotated[DecisionService, Depends(get_decision_service)]
