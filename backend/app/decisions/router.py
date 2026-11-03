"""HTTP layer only: validate the request, call the service, map "not found" to 404."""

from fastapi import APIRouter, HTTPException

from .dependencies import DecisionServiceDep
from .schema import DecisionRequest, DecisionResponse

router = APIRouter(prefix="/decisions", tags=["decisions"])


@router.post("", status_code=201)
async def create_decision(body: DecisionRequest, service: DecisionServiceDep) -> DecisionResponse:
    return await service.create(body.text)


@router.get("/{decision_id}")
def read_decision(decision_id: str, service: DecisionServiceDep) -> DecisionResponse:
    decision = service.get(decision_id)
    if decision is None:
        raise HTTPException(404, "decision not found")
    return decision
