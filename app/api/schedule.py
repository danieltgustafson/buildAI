"""Crew scheduling endpoints: import, assignments, utilization, coverage."""

from __future__ import annotations

import io
from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.auth import TokenData, require_role
from app.models.employee import Employee
from app.models.job_labor_demand import JobLaborDemand
from app.models.schedule_assignment import ScheduleAssignment
from app.schemas.schedule import (
    CoverageRow,
    EmployeeSimple,
    GenerateRequest,
    GenerateResult,
    JobLaborDemandRead,
    ScheduleAssignmentRead,
    ScheduleImportResult,
    UtilizationRow,
)
from app.services.schedule_import import import_workbook
from app.services.schedule_generator import generate_schedule

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.post("/import", response_model=ScheduleImportResult)
async def import_schedule(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin", "ops")),
):
    """Upload the crew scheduling Excel workbook (Crew + Demand + monthly grid sheets)."""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="File must be an .xlsx workbook.")
    contents = await file.read()
    result = import_workbook(io.BytesIO(contents), db)
    return result


@router.get("/assignments", response_model=list[ScheduleAssignmentRead])
def get_assignments(
    month: str | None = None,
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin", "ops", "viewer")),
):
    """Return assignments for a month (YYYY-MM). Defaults to current month."""
    ym = month or date.today().strftime("%Y-%m")
    try:
        year, mo = int(ym[:4]), int(ym[5:])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    _, days = monthrange(year, mo)
    start = date(year, mo, 1)
    end = date(year, mo, days)

    rows = (
        db.query(ScheduleAssignment)
        .filter(ScheduleAssignment.work_date >= start, ScheduleAssignment.work_date <= end)
        .all()
    )

    result = []
    for r in rows:
        result.append(ScheduleAssignmentRead(
            assignment_id=r.assignment_id,
            employee_id=r.employee_id,
            employee_name=r.employee.name if r.employee else "Unknown",
            crew_type=r.employee.crew_type if r.employee else None,
            job_id=r.job_id,
            job_name=r.job.job_name if r.job else r.notes,
            work_date=r.work_date,
        ))
    return result


@router.get("/utilization", response_model=list[UtilizationRow])
def get_utilization(
    month: str | None = None,
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin", "ops", "viewer")),
):
    """Per-person utilization for a month: assigned days vs available work days."""
    ym = month or date.today().strftime("%Y-%m")
    try:
        year, mo = int(ym[:4]), int(ym[5:])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    _, days = monthrange(year, mo)
    start = date(year, mo, 1)
    end = date(year, mo, days)

    # Count weekdays (Mon-Fri) in month as available days
    available = sum(
        1 for d in range(1, days + 1) if date(year, mo, d).weekday() < 5
    )

    assignments = (
        db.query(ScheduleAssignment)
        .filter(ScheduleAssignment.work_date >= start, ScheduleAssignment.work_date <= end)
        .all()
    )

    assigned_by_emp: dict = {}
    for a in assignments:
        assigned_by_emp.setdefault(a.employee_id, 0)
        assigned_by_emp[a.employee_id] += 1

    employees = db.query(Employee).all()
    result = []
    for emp in employees:
        assigned = assigned_by_emp.get(emp.employee_id, 0)
        result.append(UtilizationRow(
            employee_id=emp.employee_id,
            employee_name=emp.name,
            crew_type=emp.crew_type,
            available_days=available,
            assigned_days=assigned,
            utilization_pct=round(assigned / available * 100, 1) if available else 0,
        ))

    return sorted(result, key=lambda r: r.employee_name)


@router.get("/coverage", response_model=list[CoverageRow])
def get_coverage(
    month: str | None = None,
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin", "ops", "viewer")),
):
    """Demand vs assigned man-days per job for a month."""
    ym = month or date.today().strftime("%Y-%m")
    try:
        year, mo = int(ym[:4]), int(ym[5:])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    _, days = monthrange(year, mo)
    start = date(year, mo, 1)
    end = date(year, mo, days)

    demands = db.query(JobLaborDemand).filter_by(year_month=ym).all()

    assignments = (
        db.query(ScheduleAssignment)
        .filter(
            ScheduleAssignment.work_date >= start,
            ScheduleAssignment.work_date <= end,
            ScheduleAssignment.job_id.isnot(None),
        )
        .all()
    )

    # Count assigned days per (job_id, crew_type)
    assigned_map: dict[tuple, int] = {}
    for a in assignments:
        crew_type = a.employee.crew_type if a.employee else None
        key = (a.job_id, crew_type)
        assigned_map[key] = assigned_map.get(key, 0) + 1

    result = []
    for d in demands:
        key = (d.job_id, d.crew_type)
        assigned = assigned_map.get(key, 0)
        result.append(CoverageRow(
            job_id=d.job_id,
            job_name=d.job.job_name if d.job else str(d.job_id),
            year_month=d.year_month,
            crew_type=d.crew_type,
            man_days_needed=float(d.man_days_needed),
            man_days_assigned=assigned,
            gap=assigned - float(d.man_days_needed),
        ))

    return sorted(result, key=lambda r: (r.job_name, r.crew_type or ""))


@router.get("/employees", response_model=list[EmployeeSimple])
def list_employees(
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin", "ops", "viewer")),
):
    """All employees with name and crew type — used to build absence checkboxes."""
    employees = db.query(Employee).order_by(
        Employee.ranking_score.desc().nullslast(), Employee.name
    ).all()
    return [EmployeeSimple(
        employee_id=e.employee_id,
        name=e.name,
        crew_type=e.crew_type,
        ranking_score=e.ranking_score,
        ranking_title=e.ranking_title,
    ) for e in employees]


@router.post("/generate", response_model=GenerateResult)
def generate_draft_schedule(
    req: GenerateRequest,
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin", "ops")),
):
    """Generate a proportional draft schedule for a month.

    Distributes available crew across jobs in proportion to each job's
    remaining monthly man-day demand. Pass absent_employee_ids to exclude
    crew members who are unavailable for the month.
    """
    result = generate_schedule(
        month=req.month,
        absent_employee_ids=set(req.absent_employee_ids),
        db=db,
        clear_existing=req.clear_existing,
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result
