from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.schemas.building_research import ResearchRequest, ResearchResponse
from app.services.building_research import run_building_system_research

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/building-systems", response_model=ResearchResponse)
def research_building_systems(
    payload: ResearchRequest,
    _user=Depends(get_current_user),
):
    """Research likely ages of major building systems from public-record style inputs."""
    return run_building_system_research(payload)
