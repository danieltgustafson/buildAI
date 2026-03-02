from __future__ import annotations

"""Job listing and detail endpoints."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.job import Job, JobStatus
from app.schemas.job import JobCostSummary, JobCreate, JobRead
from app.services.cost_engine import job_cost_summary

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobRead])
def list_jobs(
    status: JobStatus | None = None,
    customer: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """List jobs with optional filters."""
    q = db.query(Job)
    if status:
        q = q.filter(Job.status == status)
    if customer:
        q = q.filter(Job.customer_name.ilike(f"%{customer}%"))
    if search:
        q = q.filter(Job.job_name.ilike(f"%{search}%"))
    return q.order_by(Job.job_name).all()


@router.post("", response_model=JobRead, status_code=201)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Create a new job."""
    job = Job(**payload.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("/{job_id}", response_model=JobRead)
def get_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Get a single job by ID."""
    return db.query(Job).filter(Job.job_id == job_id).one()


@router.get("/{job_id}/summary", response_model=JobCostSummary)
def get_job_summary(
    job_id: UUID,
    as_of: date | None = Query(None, description="As-of date for the summary"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Get job cost summary: planned vs actual labor, materials, total cost, margin."""
    return job_cost_summary(db, job_id, as_of)
