"""Parse and import the RSI crew scheduling Excel workbook.

Actual workbook layout (Crew Summary 2025.xlsx):

  "Employee Contact Information"
      Columns: FIRST NAME | LAST NAME | COMPANY ROLE | ...
      One row per employee; COMPANY ROLE is the crew type.

  "Man Day Count"
      Row 0 header: Job | January | February | ... | December | Total
      Rows 1+: job name in col 0, man-day count per month (NaN = 0).
      Year is passed in as a parameter (default 2025).

  "January" … "December"  (one sheet per month)
      Row 0: day-of-week labels (ignored for import; may contain notes).
      Row 1: actual datetime objects for each work column (col 0 is NaN).
      Rows 2+: employee rows until a NaN name or the "Subs" separator.
          Col 0  = employee name (short forms used; fuzzy-matched to DB).
          Col 1+ = job name for that date, or NaN / "OUT" / "VACATION" /
                   "OFF" (= not on a job, skip).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.job import Job
from app.models.job_labor_demand import JobLaborDemand
from app.models.schedule_assignment import ScheduleAssignment

# Month names → zero-padded month number
_MONTH_NUM = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

# Cell values that mean "not working / no assignment"
_NON_WORK = {"out", "vacation", "off", "nan", "", "holiday"}

# Sheet names that are the monthly grids
_MONTHLY_SHEETS = set(_MONTH_NUM.keys())


def _clean(val: Any) -> str:
    return str(val).strip() if val is not None else ""


def _is_non_work(val: Any) -> bool:
    s = _clean(val).lower()
    return not s or s == "nan" or any(s.startswith(k) for k in _NON_WORK)


def _build_name_index(employees: list[Employee]) -> dict[str, Employee]:
    """
    Build a lookup dict from every plausible name variant → Employee.
    Handles cases like "Dawud (Ali) Billa" → also keyed as "ali" and "dawud".
    """
    idx: dict[str, Employee] = {}

    for emp in employees:
        full = emp.name.strip().lower()
        idx[full] = emp

        parts = full.split()
        # first word
        if parts:
            idx[parts[0]] = emp
        # last word
        if len(parts) > 1:
            idx[parts[-1]] = emp
        # handle "Name (Alias) Surname" → also index the alias without parens
        for part in parts:
            if part.startswith("(") and part.endswith(")"):
                alias = part[1:-1].lower()
                idx[alias] = emp

    return idx


def _match_employee(
    raw_name: str,
    name_idx: dict[str, Employee],
    db: Session,
    warnings: list[str],
) -> Employee | None:
    key = raw_name.strip().lower()
    if not key or key == "nan":
        return None

    # Exact or partial match in index
    if key in name_idx:
        return name_idx[key]

    # Try first token only
    first_token = key.split()[0] if key.split() else key
    if first_token in name_idx:
        return name_idx[first_token]

    # Prefix match — handles "Heri" → "Heriberto", "Marco Q" → "Marco Quevedo"
    prefix_matches = [e for k, e in name_idx.items() if k.startswith(first_token) and len(first_token) >= 3]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        warnings.append(f"Ambiguous name '{raw_name}' — matched multiple employees, using first.")

    # Create a new employee record so we don't lose assignments
    warnings.append(f"Employee '{raw_name}' not in contact sheet — created as new record.")
    emp = Employee(name=raw_name.strip())
    db.add(emp)
    db.flush()
    # Add to index so subsequent rows match
    name_idx[raw_name.strip().lower()] = emp
    return emp


def import_workbook(path_or_bytes: Any, db: Session, demand_year: int = 2025) -> dict:
    warnings: list[str] = []
    xl = pd.ExcelFile(path_or_bytes, engine="openpyxl")

    # ── 1. Crew / Employee Contact Information ──────────────────────────────
    crew_sheet = next(
        (s for s in xl.sheet_names if "employee" in s.lower() or "contact" in s.lower()),
        None,
    )
    employees_updated = 0

    if crew_sheet:
        df = xl.parse(crew_sheet, header=0, dtype=str).fillna("")
        cols_lower = {c.strip().lower(): c for c in df.columns}

        fn_col = next((cols_lower[k] for k in cols_lower if "first" in k), None)
        ln_col = next((cols_lower[k] for k in cols_lower if "last" in k), None)
        role_col = next((cols_lower[k] for k in cols_lower if "role" in k), None)

        for _, row in df.iterrows():
            first = _clean(row.get(fn_col, "")) if fn_col else ""
            last = _clean(row.get(ln_col, "")) if ln_col else ""
            full_name = f"{first} {last}".strip()
            if not full_name or full_name.lower() in ("nan", "nan nan"):
                continue

            crew_type = _clean(row.get(role_col, "")) if role_col else None
            if not crew_type or crew_type.lower() == "nan":
                crew_type = None

            emp = db.query(Employee).filter(Employee.name.ilike(full_name)).first()
            if emp is None:
                # Also try first-name-only match
                emp = db.query(Employee).filter(Employee.name.ilike(f"{first}%")).first()
            if emp is None:
                emp = Employee(name=full_name, crew_type=crew_type)
                db.add(emp)
            else:
                emp.name = full_name  # normalize to full name
                if crew_type:
                    emp.crew_type = crew_type
            employees_updated += 1

        db.flush()
    else:
        warnings.append("No 'Employee Contact Information' sheet found; skipping crew import.")

    # Rebuild name index after crew upsert
    all_employees = db.query(Employee).all()
    name_idx = _build_name_index(all_employees)

    all_jobs: dict[str, Job] = {j.job_name.strip().lower(): j for j in db.query(Job).all()}

    # ── 2. Man Day Count (demand) ───────────────────────────────────────────
    demand_sheet = next(
        (s for s in xl.sheet_names if "man day" in s.lower() or "demand" in s.lower()),
        None,
    )
    demand_rows_upserted = 0

    if demand_sheet:
        df = xl.parse(demand_sheet, header=0, dtype=str).fillna("")
        job_col = df.columns[0]

        for _, row in df.iterrows():
            job_name = _clean(row[job_col])
            if not job_name or job_name.lower() in ("nan", "job", "total"):
                continue

            job = all_jobs.get(job_name.lower())
            if job is None:
                warnings.append(f"Demand: job '{job_name}' not in DB — skipped.")
                continue

            for col in df.columns[1:]:
                month_key = _clean(col).lower()
                if month_key not in _MONTH_NUM:
                    continue  # skip "Total" and unrecognised columns
                ym = f"{demand_year}-{_MONTH_NUM[month_key]}"
                try:
                    val = float(_clean(row[col]) or "0")
                except ValueError:
                    continue

                existing = (
                    db.query(JobLaborDemand)
                    .filter_by(job_id=job.job_id, year_month=ym, crew_type=None)
                    .first()
                )
                if existing:
                    existing.man_days_needed = val
                else:
                    db.add(JobLaborDemand(
                        job_id=job.job_id,
                        year_month=ym,
                        crew_type=None,
                        man_days_needed=val,
                    ))
                demand_rows_upserted += 1

        db.flush()
    else:
        warnings.append("No 'Man Day Count' sheet found; skipping demand import.")

    # ── 3. Monthly schedule grids ───────────────────────────────────────────
    assignments_upserted = 0

    for sheet_name in xl.sheet_names:
        if sheet_name.strip().lower() not in _MONTHLY_SHEETS:
            continue

        month_num = _MONTH_NUM[sheet_name.strip().lower()]

        # Parse with no header so we control row access
        df = xl.parse(sheet_name, header=None)
        if df.shape[0] < 3 or df.shape[1] < 2:
            continue

        # Row 1 (index 1): actual date objects in columns 1+
        date_row = df.iloc[1, 1:]
        date_cols: dict[int, date] = {}  # col index → date
        for col_idx, val in enumerate(date_row, start=1):
            if isinstance(val, (datetime, pd.Timestamp)):
                d = val.date() if hasattr(val, "date") else val
                date_cols[col_idx] = d

        if not date_cols:
            warnings.append(f"Sheet '{sheet_name}': no parseable dates in row 1 — skipped.")
            continue

        # Rows 2+: employee rows until NaN name or "Subs" / summary section
        for row_idx in range(2, df.shape[0]):
            raw_name = _clean(df.iloc[row_idx, 0])

            # Stop at subcontractor separator or blank region
            if raw_name.lower() in ("nan", "", "subs", "man day count", "leaks", "sent proposals"):
                break
            if raw_name.lower().startswith("jobs"):
                break

            emp = _match_employee(raw_name, name_idx, db, warnings)
            if emp is None:
                continue

            for col_idx, work_date in date_cols.items():
                if col_idx >= df.shape[1]:
                    continue
                cell = df.iloc[row_idx, col_idx]
                if _is_non_work(cell):
                    continue

                job_name_raw = _clean(cell)
                # Strip parenthetical notes like "(half day)"
                job_name_clean = job_name_raw.split("(")[0].strip()
                # Handle "Job A/Job B" — take first job listed
                job_name_clean = job_name_clean.split("/")[0].strip()

                job = all_jobs.get(job_name_clean.lower())
                job_id = job.job_id if job else None
                note = job_name_raw if job is None else None
                if job is None:
                    warnings.append(
                        f"Sheet '{sheet_name}' {work_date} {raw_name}: "
                        f"job '{job_name_clean}' not in DB — stored in notes."
                    )

                existing = (
                    db.query(ScheduleAssignment)
                    .filter_by(employee_id=emp.employee_id, work_date=work_date)
                    .first()
                )
                if existing:
                    existing.job_id = job_id
                    existing.notes = note
                else:
                    db.add(ScheduleAssignment(
                        employee_id=emp.employee_id,
                        job_id=job_id,
                        work_date=work_date,
                        notes=note,
                    ))
                assignments_upserted += 1

    db.commit()

    return {
        "employees_updated": employees_updated,
        "demand_rows_upserted": demand_rows_upserted,
        "assignments_upserted": assignments_upserted,
        "warnings": warnings,
    }
