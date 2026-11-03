"""Database access for decisions. The only module that queries the decisions table."""

from typing import TYPE_CHECKING

from .models import DecisionRow

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class DecisionRepository:
    """Reads and appends rows of the decision log."""

    def __init__(self, session: Session) -> None:
        """Use the given session for every query."""
        self._session = session

    def add(self, row: DecisionRow) -> DecisionRow:
        """Store a new decision and commit it."""
        self._session.add(row)
        self._session.commit()
        return row

    def get(self, decision_id: str) -> DecisionRow | None:
        """Return the decision with this id, or None if there is none."""
        return self._session.get(DecisionRow, decision_id)
