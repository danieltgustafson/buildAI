from __future__ import annotations

"""WIP (Work in Progress) report endpoints."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.schemas.wip import WIPReport
from app.services.wip_engine import compute_wip

router = APIRouter(prefix="/wip", tags=["wip"])


@router.get("", response_model=list[WIPReport])
def get_wip_report(
    as_of: date | None = Query(None, description="As-of date for WIP calculations"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Get WIP report for all active jobs.

    Shows contract value, cost-to-date, percent complete, earned revenue,
    and over/under billing for each job.
    """
    return compute_wip(db, as_of)
