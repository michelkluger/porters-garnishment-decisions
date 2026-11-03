"""Database access for decisions. The only module that queries the decisions table."""

from sqlalchemy.orm import Session

from .models import DecisionRow


class DecisionRepository:
    def __init__(self, session: Session):
        self._session = session

    def add(self, row: DecisionRow) -> DecisionRow:
        self._session.add(row)
        self._session.commit()
        return row

    def get(self, decision_id: str) -> DecisionRow | None:
        return self._session.get(DecisionRow, decision_id)
