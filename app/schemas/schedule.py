from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel


class ScheduleAssignmentRead(BaseModel):
    assignment_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    crew_type: Optional[str]
    job_id: Optional[uuid.UUID]
    job_name: Optional[str]
    work_date: date

    model_config = {"from_attributes": True}


class JobLaborDemandRead(BaseModel):
    demand_id: uuid.UUID
    job_id: uuid.UUID
    job_name: str
    year_month: str
    crew_type: Optional[str]
    man_days_needed: float

    model_config = {"from_attributes": True}


class UtilizationRow(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    crew_type: Optional[str]
    available_days: int
    assigned_days: int
    utilization_pct: float


class CoverageRow(BaseModel):
    job_id: uuid.UUID
    job_name: str
    year_month: str
    crew_type: Optional[str]
    man_days_needed: float
    man_days_assigned: int
    gap: float  # negative = understaffed, positive = surplus


class ScheduleImportResult(BaseModel):
    employees_updated: int
    demand_rows_upserted: int
    assignments_upserted: int
    warnings: list[str]


class EmployeeSimple(BaseModel):
    employee_id: uuid.UUID
    name: str
    crew_type: Optional[str]
    ranking_score: Optional[int]
    ranking_title: Optional[str]

    model_config = {"from_attributes": True}


class GenerateRequest(BaseModel):
    month: str                          # YYYY-MM
    absent_employee_ids: list[str] = [] # employee_ids (as strings) absent the whole month
    clear_existing: bool = True


class GenerateResult(BaseModel):
    month: str
    working_days: int
    available_crew: int
    total_supply_days: int
    total_demand_days: int
    assignments_created: int
    demand_unmet_days: int
    demand_met_pct: float
    crew_utilization_pct: float
