from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.models.job import JobStatus


class JobBase(BaseModel):
    job_name: str
    external_job_ref: str | None = None
    customer_name: str | None = None
    site_address: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    contract_value: float | None = None
    retainage_pct: float | None = None
    status: JobStatus = JobStatus.active


class JobCreate(JobBase):
    pass


class JobRead(JobBase):
    job_id: UUID

    model_config = {"from_attributes": True}


class JobCostSummary(BaseModel):
    job_id: UUID
    job_name: str
    customer_name: str | None = None
    contract_value: float | None = None
    status: str

    # budget
    planned_labor_hours: float | None = None
    planned_labor_cost: float | None = None
    planned_material_cost: float | None = None
    planned_sub_cost: float | None = None
    planned_total_cost: float | None = None

    # actuals
    actual_labor_hours: float = 0
    actual_labor_cost: float = 0
    actual_nonlabor_cost: float = 0
    actual_total_cost: float = 0

    # billing
    billed_to_date: float = 0

    # derived
    margin_to_date: float | None = None
    labor_hours_variance: float | None = None
