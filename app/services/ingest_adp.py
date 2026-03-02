from __future__ import annotations

"""ADP payroll/time CSV ingestion service."""

import hashlib
import io
from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.exception import Exception as ExceptionModel
from app.models.exception import ExceptionSeverity, ExceptionType
from app.models.job_mapping import JobMapping
from app.models.time_entry import TimeEntry
from app.schemas.ingest import IngestResult
from app.services.cost_engine import compute_burdened_cost, get_burden_rate


# Expected CSV columns (flexible -- we map what we find)
EXPECTED_COLUMNS = {
    "employee_id": ["employee_id", "emp_id", "associate_id", "worker_id"],
    "employee_name": ["employee_name", "name", "worker_name", "associate_name"],
    "work_date": ["work_date", "date", "pay_date", "period_date"],
    "hours": ["hours", "regular_hours", "total_hours", "hrs"],
    "pay_rate": ["pay_rate", "rate", "hourly_rate"],
    "job_ref": ["job", "project", "department", "job_code", "project_code", "dept"],
    "gross_pay": ["gross_pay", "gross", "earnings", "total_pay"],
}


def _resolve_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        matches = [col for col in df.columns if col.strip().lower() == c.lower()]
        if matches:
            return matches[0]
    return None


def ingest_adp_csv(db: Session, file_content: bytes, filename: str) -> IngestResult:
    """Parse an ADP time/payroll CSV and load into time_entries."""
    file_hash = hashlib.sha256(file_content).hexdigest()[:16]

    df = pd.read_csv(io.BytesIO(file_content))
    df.columns = df.columns.str.strip()

    col_map = {}
    for key, candidates in EXPECTED_COLUMNS.items():
        col_map[key] = _resolve_column(df, candidates)

    if col_map["hours"] is None and col_map["gross_pay"] is None:
        return IngestResult(
            source="adp",
            rows_ingested=0,
            rows_mapped=0,
            rows_unmapped=0,
            exceptions_created=0,
            message="Could not find hours or gross_pay column in CSV",
        )

    burden = get_burden_rate(db, date.today())
    rows_ingested = 0
    rows_mapped = 0
    rows_unmapped = 0
    exceptions_created = 0

    for _, row in df.iterrows():
        # Resolve or create employee
        emp_ref = str(row[col_map["employee_id"]]).strip() if col_map["employee_id"] else None
        emp_name = str(row[col_map["employee_name"]]).strip() if col_map["employee_name"] else "Unknown"

        employee = None
        if emp_ref:
            employee = (
                db.query(Employee).filter(Employee.adp_employee_ref == emp_ref).first()
            )
            if not employee:
                employee = Employee(adp_employee_ref=emp_ref, name=emp_name)
                db.add(employee)
                db.flush()

        # Parse fields
        work_date_raw = row[col_map["work_date"]] if col_map["work_date"] else None
        try:
            work_date_val = pd.to_datetime(work_date_raw).date()
        except Exception:
            work_date_val = date.today()

        hours = float(row[col_map["hours"]]) if col_map["hours"] and pd.notna(row[col_map["hours"]]) else 0
        pay_rate = (
            float(row[col_map["pay_rate"]])
            if col_map["pay_rate"] and pd.notna(row.get(col_map["pay_rate"]))
            else None
        )
        gross_pay = (
            float(row[col_map["gross_pay"]])
            if col_map["gross_pay"] and pd.notna(row.get(col_map["gross_pay"]))
            else None
        )

        # Resolve job mapping
        job_ref = str(row[col_map["job_ref"]]).strip() if col_map["job_ref"] and pd.notna(row.get(col_map["job_ref"])) else None
        job_id = None
        if job_ref:
            mapping = (
                db.query(JobMapping)
                .filter(JobMapping.source_system == "adp", JobMapping.source_key == job_ref)
                .first()
            )
            if mapping and mapping.job_id:
                job_id = mapping.job_id
                rows_mapped += 1
            else:
                rows_unmapped += 1
                # Create exception for unmapped entry
                existing_exc = (
                    db.query(ExceptionModel)
                    .filter(
                        ExceptionModel.type == ExceptionType.UNMAPPED_TIME_ENTRY,
                        ExceptionModel.source_ref == f"adp:{job_ref}",
                        ExceptionModel.resolved_at.is_(None),
                    )
                    .first()
                )
                if not existing_exc:
                    db.add(
                        ExceptionModel(
                            type=ExceptionType.UNMAPPED_TIME_ENTRY,
                            severity=ExceptionSeverity.warn,
                            message=f"ADP time entry has unmapped job ref: {job_ref}",
                            source_ref=f"adp:{job_ref}",
                        )
                    )
                    exceptions_created += 1
        else:
            rows_unmapped += 1

        # Compute costs
        dc, bc = compute_burdened_cost(hours, pay_rate, gross_pay, burden)

        raw_source_id = f"adp:{file_hash}:{rows_ingested}"
        entry = TimeEntry(
            job_id=job_id,
            employee_id=employee.employee_id if employee else None,
            work_date=work_date_val,
            hours=hours,
            pay_rate=pay_rate,
            raw_source_id=raw_source_id,
            labor_cost_direct=dc,
            labor_cost_burdened=bc,
        )
        db.add(entry)
        rows_ingested += 1

    db.commit()

    return IngestResult(
        source="adp",
        rows_ingested=rows_ingested,
        rows_mapped=rows_mapped,
        rows_unmapped=rows_unmapped,
        exceptions_created=exceptions_created,
        message=f"Ingested {rows_ingested} ADP time entries from {filename}",
    )
