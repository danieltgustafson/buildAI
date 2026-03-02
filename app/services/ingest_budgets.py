from __future__ import annotations

"""Budget/estimate CSV ingestion service."""

import io

import pandas as pd
from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.job_budget import JobBudget
from app.schemas.ingest import IngestResult


EXPECTED_COLUMNS = {
    "job_name": ["job_name", "job", "project", "project_name"],
    "job_ref": ["job_ref", "job_id", "external_ref", "job_code"],
    "planned_revenue": ["planned_revenue", "revenue", "contract_value", "total_revenue"],
    "planned_labor_hours": ["planned_labor_hours", "labor_hours", "total_hours", "hours"],
    "planned_labor_cost": ["planned_labor_cost", "labor_cost", "labor_budget"],
    "planned_material_cost": ["planned_material_cost", "material_cost", "materials_budget", "materials"],
    "planned_sub_cost": ["planned_sub_cost", "sub_cost", "subcontractor_cost", "subs"],
}


def _resolve_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        matches = [col for col in df.columns if col.strip().lower() == c.lower()]
        if matches:
            return matches[0]
    return None


def ingest_budgets_csv(db: Session, file_content: bytes, filename: str) -> IngestResult:
    """Parse a budget/estimate CSV and create or update job budgets."""
    df = pd.read_csv(io.BytesIO(file_content))
    df.columns = df.columns.str.strip()

    col_map = {}
    for key, candidates in EXPECTED_COLUMNS.items():
        col_map[key] = _resolve_column(df, candidates)

    rows_ingested = 0
    rows_mapped = 0
    rows_unmapped = 0

    for _, row in df.iterrows():
        job_name = str(row[col_map["job_name"]]).strip() if col_map["job_name"] and pd.notna(row.get(col_map["job_name"])) else None
        job_ref = str(row[col_map["job_ref"]]).strip() if col_map["job_ref"] and pd.notna(row.get(col_map["job_ref"])) else None

        # Find the job
        job = None
        if job_ref:
            job = db.query(Job).filter(Job.external_job_ref == job_ref).first()
        if not job and job_name:
            job = db.query(Job).filter(Job.job_name == job_name).first()

        if not job:
            rows_unmapped += 1
            continue

        rows_mapped += 1

        def _safe_float(col_key):
            col = col_map.get(col_key)
            if col and pd.notna(row.get(col)):
                try:
                    return float(row[col])
                except (ValueError, TypeError):
                    return None
            return None

        # Get next budget version
        latest = (
            db.query(JobBudget)
            .filter(JobBudget.job_id == job.job_id)
            .order_by(JobBudget.budget_version.desc())
            .first()
        )
        next_version = (latest.budget_version + 1) if latest else 1

        budget = JobBudget(
            job_id=job.job_id,
            budget_version=next_version,
            planned_revenue=_safe_float("planned_revenue"),
            planned_labor_hours=_safe_float("planned_labor_hours"),
            planned_labor_cost=_safe_float("planned_labor_cost"),
            planned_material_cost=_safe_float("planned_material_cost"),
            planned_sub_cost=_safe_float("planned_sub_cost"),
        )
        db.add(budget)

        # Also update contract_value on job if planned_revenue provided
        rev = _safe_float("planned_revenue")
        if rev and (job.contract_value is None or float(job.contract_value) == 0):
            job.contract_value = rev

        rows_ingested += 1

    db.commit()

    return IngestResult(
        source="budgets",
        rows_ingested=rows_ingested,
        rows_mapped=rows_mapped,
        rows_unmapped=rows_unmapped,
        exceptions_created=0,
        message=f"Ingested {rows_ingested} budgets from {filename} ({rows_unmapped} unmatched jobs)",
    )
