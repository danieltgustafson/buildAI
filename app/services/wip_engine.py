from __future__ import annotations

"""WIP (Work in Progress) engine: earned value and over/under billing."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.gl_transaction import GLTransaction
from app.models.job import Job, JobStatus
from app.models.job_billing import JobBilling
from app.models.job_budget import JobBudget
from app.models.time_entry import TimeEntry
from app.schemas.wip import WIPReport


def compute_wip(db: Session, as_of: date | None = None) -> list[WIPReport]:
    """Compute WIP report for all active jobs."""
    jobs = db.query(Job).filter(Job.status == JobStatus.active).all()
    reports = []
    for job in jobs:
        reports.append(_wip_for_job(db, job, as_of))
    return reports


def wip_for_job(db: Session, job_id, as_of: date | None = None) -> WIPReport:
    job = db.query(Job).filter(Job.job_id == job_id).one()
    return _wip_for_job(db, job, as_of)


def _wip_for_job(db: Session, job: Job, as_of: date | None) -> WIPReport:
    # latest budget
    budget = (
        db.query(JobBudget)
        .filter(JobBudget.job_id == job.job_id)
        .order_by(JobBudget.budget_version.desc())
        .first()
    )

    # actual labor cost
    labor_q = db.query(
        func.coalesce(func.sum(TimeEntry.hours), Decimal(0)).label("hours"),
        func.coalesce(func.sum(TimeEntry.labor_cost_burdened), Decimal(0)).label("cost"),
    ).filter(TimeEntry.job_id == job.job_id)
    if as_of:
        labor_q = labor_q.filter(TimeEntry.work_date <= as_of)
    labor = labor_q.one()

    # actual non-labor
    nonlabor_q = db.query(
        func.coalesce(func.sum(GLTransaction.amount), Decimal(0)).label("cost"),
    ).filter(GLTransaction.job_id == job.job_id)
    if as_of:
        nonlabor_q = nonlabor_q.filter(GLTransaction.txn_date <= as_of)
    nonlabor = nonlabor_q.one()

    # billing
    billing_q = db.query(
        func.coalesce(func.sum(JobBilling.amount_billed), Decimal(0)).label("billed"),
    ).filter(JobBilling.job_id == job.job_id)
    if as_of:
        billing_q = billing_q.filter(JobBilling.invoice_date <= as_of)
    billing = billing_q.one()

    actual_labor_hours = float(labor.hours)
    actual_labor_cost = float(labor.cost)
    actual_nonlabor_cost = float(nonlabor.cost)
    actual_total_cost = actual_labor_cost + actual_nonlabor_cost
    billed_to_date = float(billing.billed)

    contract_value = float(job.contract_value) if job.contract_value else None
    budget_total_cost = None
    pct_complete = None
    earned_revenue = None
    over_under_billing = None
    flags: list[str] = []

    if budget:
        budget_total_cost = sum(
            float(v or 0)
            for v in [budget.planned_labor_cost, budget.planned_material_cost, budget.planned_sub_cost]
        )

        if budget_total_cost and budget_total_cost > 0:
            raw_pct = actual_total_cost / budget_total_cost
            pct_complete = min(raw_pct, 1.2)  # cap at 120%

            if raw_pct > 1.0:
                flags.append("JOB_OVERRUN_RISK")

        elif budget.planned_labor_hours and float(budget.planned_labor_hours) > 0:
            # fallback: use labor hours as proxy
            raw_pct = actual_labor_hours / float(budget.planned_labor_hours)
            pct_complete = min(raw_pct, 1.2)

            if raw_pct > 1.0:
                flags.append("JOB_OVERRUN_RISK")

        if pct_complete is not None and contract_value:
            earned_revenue = round(pct_complete * contract_value, 2)
            over_under_billing = round(billed_to_date - earned_revenue, 2)

    # check labor burn rate
    if budget and budget.planned_labor_hours and float(budget.planned_labor_hours) > 0:
        if actual_labor_hours > float(budget.planned_labor_hours) * 0.9 and (
            pct_complete is not None and pct_complete < 0.9
        ):
            flags.append("LABOR_BURN_RATE_HIGH")

    return WIPReport(
        job_id=job.job_id,
        job_name=job.job_name,
        customer_name=job.customer_name,
        contract_value=contract_value,
        actual_total_cost=actual_total_cost,
        budget_total_cost=budget_total_cost,
        pct_complete=round(pct_complete, 4) if pct_complete is not None else None,
        earned_revenue=earned_revenue,
        billed_to_date=billed_to_date,
        over_under_billing=over_under_billing,
        status=job.status.value,
        flags=flags,
    )
