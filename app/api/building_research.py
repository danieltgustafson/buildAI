from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.schemas.building_research import ResearchRequest, ResearchResponse
from app.services.building_research import OpenAIResearchUnavailableError, run_building_system_research

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/building-systems", response_model=ResearchResponse)
def research_building_systems(
    payload: ResearchRequest,
    _user=Depends(get_current_user),
):
    """Research likely ages of major building systems from public-record style inputs."""
    try:
        return run_building_system_research(payload)
    except OpenAIResearchUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
