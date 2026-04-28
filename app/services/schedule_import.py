"""Parse and import the crew scheduling Excel workbook.

Expected workbook layout (sheet names are matched case-insensitively):

  "Crew"    – columns: Name | Level (or Crew Type / Role)
  "Demand"  – first col: Job Name; remaining cols: month headers (e.g. "Apr 2026"
               or "2026-04") with man-day values; optional second index col for
               crew type (if the sheet has a Crew Type column before the months)
  Any other sheet is treated as a schedule grid for the month named in the tab
               title (e.g. "Apr 2026").  Columns = employee names, rows = calendar
               days (first col = date or day number), cells = job name or blank.
"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.job import Job
from app.models.job_labor_demand import JobLaborDemand
from app.models.schedule_assignment import ScheduleAssignment


def _normalize(text: Any) -> str:
    return str(text).strip().lower()


def _find_sheet(xl: pd.ExcelFile, *candidates: str) -> str | None:
    for name in xl.sheet_names:
        if _normalize(name) in {c.lower() for c in candidates}:
            return name
    return None


def _parse_month_header(header: str) -> str | None:
    """Return YYYY-MM string from a variety of month header formats, or None."""
    h = str(header).strip()
    # Already YYYY-MM
    if re.match(r"^\d{4}-\d{2}$", h):
        return h
    # "Apr 2026", "April 2026", "Apr-2026"
    for fmt in ("%b %Y", "%B %Y", "%b-%Y", "%B-%Y", "%m/%Y", "%m-%Y"):
        try:
            return datetime.strptime(h, fmt).strftime("%Y-%m")
        except ValueError:
            pass
    # "2026-Apr"
    try:
        return datetime.strptime(h, "%Y-%b").strftime("%Y-%m")
    except ValueError:
        pass
    return None


def _parse_schedule_month(sheet_name: str) -> str | None:
    """Derive YYYY-MM from the sheet tab name."""
    return _parse_month_header(sheet_name)


def import_workbook(path_or_bytes: Any, db: Session) -> dict:
    warnings: list[str] = []
    xl = pd.ExcelFile(path_or_bytes, engine="openpyxl")

    # ------------------------------------------------------------------ Crew
    crew_sheet = _find_sheet(xl, "crew", "employees", "staff", "team")
    employees_updated = 0
    if crew_sheet:
        df = xl.parse(crew_sheet, header=0, dtype=str).fillna("")
        cols = [c.strip().lower() for c in df.columns]

        name_col = next((df.columns[i] for i, c in enumerate(cols) if "name" in c), df.columns[0])
        level_col = next(
            (df.columns[i] for i, c in enumerate(cols)
             if any(k in c for k in ("level", "type", "role", "class", "trade"))),
            None,
        )

        for _, row in df.iterrows():
            raw_name = str(row[name_col]).strip()
            if not raw_name or raw_name.lower() in ("nan", "name"):
                continue
            crew_type = str(row[level_col]).strip() if level_col else None
            if crew_type and crew_type.lower() in ("nan", ""):
                crew_type = None

            emp = db.query(Employee).filter(
                Employee.name.ilike(f"%{raw_name}%")
            ).first()
            if emp is None:
                emp = Employee(name=raw_name, crew_type=crew_type)
                db.add(emp)
            else:
                if crew_type:
                    emp.crew_type = crew_type
            employees_updated += 1

        db.flush()
    else:
        warnings.append("No 'Crew' sheet found; skipping employee update.")

    # Build name → employee lookup
    all_employees: dict[str, Employee] = {
        _normalize(e.name): e for e in db.query(Employee).all()
    }
    # Build name → job lookup
    all_jobs: dict[str, Job] = {
        _normalize(j.job_name): j for j in db.query(Job).all()
    }

    # --------------------------------------------------------------- Demand
    demand_sheet = _find_sheet(xl, "demand", "labor demand", "job demand", "jobs")
    demand_rows_upserted = 0
    if demand_sheet:
        df = xl.parse(demand_sheet, header=0, dtype=str).fillna("")
        cols = list(df.columns)

        # First col is always job name; optionally second col is crew_type
        job_col = cols[0]
        rest = cols[1:]

        # Detect if second column is a crew-type column or a month header
        has_crew_type_col = rest and _parse_month_header(str(rest[0])) is None and len(rest) > 1
        crew_type_col = rest[0] if has_crew_type_col else None
        month_cols = rest[1:] if has_crew_type_col else rest

        for _, row in df.iterrows():
            job_name = str(row[job_col]).strip()
            if not job_name or job_name.lower() in ("nan", "job", "job name"):
                continue
            job = all_jobs.get(_normalize(job_name))
            if job is None:
                warnings.append(f"Demand: job '{job_name}' not found in DB – skipped.")
                continue

            row_crew_type = str(row[crew_type_col]).strip() if crew_type_col else None
            if row_crew_type and row_crew_type.lower() in ("nan", ""):
                row_crew_type = None

            for mcol in month_cols:
                ym = _parse_month_header(str(mcol))
                if not ym:
                    continue
                try:
                    val = float(str(row[mcol]).strip() or "0")
                except ValueError:
                    continue

                existing = (
                    db.query(JobLaborDemand)
                    .filter_by(job_id=job.job_id, year_month=ym, crew_type=row_crew_type)
                    .first()
                )
                if existing:
                    existing.man_days_needed = val
                else:
                    db.add(JobLaborDemand(
                        job_id=job.job_id,
                        year_month=ym,
                        crew_type=row_crew_type,
                        man_days_needed=val,
                    ))
                demand_rows_upserted += 1

        db.flush()
    else:
        warnings.append("No 'Demand' sheet found; skipping labor demand import.")

    # --------------------------------------------------------- Schedule grids
    skip_names = {
        _normalize(s)
        for s in [crew_sheet or "", demand_sheet or ""]
        if s
    }
    assignments_upserted = 0

    for sheet_name in xl.sheet_names:
        if _normalize(sheet_name) in skip_names:
            continue

        ym = _parse_schedule_month(sheet_name)
        if not ym:
            warnings.append(f"Sheet '{sheet_name}': cannot parse as month – skipped.")
            continue

        year, month = int(ym[:4]), int(ym[5:])
        _, days_in_month = monthrange(year, month)

        df = xl.parse(sheet_name, header=0, dtype=str).fillna("")
        if df.empty or df.shape[1] < 2:
            continue

        # First column = day numbers or dates; remaining = employee names
        day_col = df.columns[0]
        emp_cols = df.columns[1:]

        for _, row in df.iterrows():
            raw_day = str(row[day_col]).strip()
            # Parse day number
            try:
                day_num = int(float(raw_day))
            except ValueError:
                # Try parsing as a date
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y"):
                    try:
                        day_num = datetime.strptime(raw_day, fmt).day
                        break
                    except ValueError:
                        pass
                else:
                    continue

            if not (1 <= day_num <= days_in_month):
                continue

            work_date = date(year, month, day_num)

            for ecol in emp_cols:
                job_name = str(row[ecol]).strip()
                if not job_name or job_name.lower() == "nan":
                    continue

                emp = all_employees.get(_normalize(str(ecol).strip()))
                if emp is None:
                    warnings.append(
                        f"Sheet '{sheet_name}': employee '{ecol}' not found – skipped."
                    )
                    continue

                job = all_jobs.get(_normalize(job_name))
                job_id = job.job_id if job else None
                if job is None:
                    warnings.append(
                        f"Sheet '{sheet_name}' day {day_num}: job '{job_name}' not found – "
                        f"assignment stored without job link."
                    )

                existing = (
                    db.query(ScheduleAssignment)
                    .filter_by(employee_id=emp.employee_id, work_date=work_date)
                    .first()
                )
                if existing:
                    existing.job_id = job_id
                    existing.notes = job_name if job is None else None
                else:
                    db.add(ScheduleAssignment(
                        employee_id=emp.employee_id,
                        job_id=job_id,
                        work_date=work_date,
                        notes=job_name if job is None else None,
                    ))
                assignments_upserted += 1

    db.commit()

    return {
        "employees_updated": employees_updated,
        "demand_rows_upserted": demand_rows_upserted,
        "assignments_upserted": assignments_upserted,
        "warnings": warnings,
    }
