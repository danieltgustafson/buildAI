from __future__ import annotations

"""Cost engine: burdened labor computation and job cost rollups."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.gl_transaction import GLTransaction
from app.models.job import Job
from app.models.job_billing import JobBilling
from app.models.job_budget import JobBudget
from app.models.labor_burden_rate import LaborBurdenRate
from app.models.time_entry import TimeEntry
from app.schemas.job import JobCostSummary


def get_burden_rate(db: Session, as_of: date) -> LaborBurdenRate | None:
    """Get the most recent burden rate effective on or before as_of."""
    return (
        db.query(LaborBurdenRate)
        .filter(LaborBurdenRate.effective_date <= as_of)
        .order_by(LaborBurdenRate.effective_date.desc())
        .first()
    )


def compute_burdened_cost(
    hours: float,
    pay_rate: float | None,
    direct_cost: float | None,
    burden: LaborBurdenRate | None,
) -> tuple[float, float]:
    """Compute direct and burdened labor cost for a time entry.

    Returns (direct_cost, burdened_cost).
    """
    if direct_cost is not None:
        dc = float(direct_cost)
    elif pay_rate is not None:
        dc = float(hours) * float(pay_rate)
    else:
        dc = 0.0

    if burden is None:
        return dc, dc

    pct_sum = sum(
        float(v or 0)
        for v in [burden.fica_pct, burden.futa_pct, burden.suta_pct, burden.workers_comp_pct]
    )
    overhead = float(burden.overhead_multiplier or 0)
    multiplier = 1.0 + pct_sum + overhead

    benefits = float(burden.benefits_per_hour or 0) * float(hours)
    burdened = dc * multiplier + benefits
    return dc, round(burdened, 2)


def recompute_time_entry_costs(db: Session, as_of: date | None = None) -> int:
    """Recompute burdened costs for all time entries. Returns count updated."""
    if as_of is None:
        as_of = date.today()

    burden = get_burden_rate(db, as_of)
    entries = db.query(TimeEntry).all()
    count = 0
    for entry in entries:
        dc, bc = compute_burdened_cost(
            float(entry.hours or 0),
            float(entry.pay_rate) if entry.pay_rate else None,
            float(entry.labor_cost_direct) if entry.labor_cost_direct else None,
            burden,
        )
        entry.labor_cost_direct = dc
        entry.labor_cost_burdened = bc
        count += 1
    db.commit()
    return count


def job_cost_summary(db: Session, job_id, as_of: date | None = None) -> JobCostSummary:
    """Compute the job cost summary for a single job."""
    job = db.query(Job).filter(Job.job_id == job_id).one()

    # latest budget
    budget = (
        db.query(JobBudget)
        .filter(JobBudget.job_id == job_id)
        .order_by(JobBudget.budget_version.desc())
        .first()
    )

    # actual labor
    labor_q = db.query(
        func.coalesce(func.sum(TimeEntry.hours), Decimal(0)).label("hours"),
        func.coalesce(func.sum(TimeEntry.labor_cost_burdened), Decimal(0)).label("cost"),
    ).filter(TimeEntry.job_id == job_id)
    if as_of:
        labor_q = labor_q.filter(TimeEntry.work_date <= as_of)
    labor = labor_q.one()

    # actual non-labor
    nonlabor_q = db.query(
        func.coalesce(func.sum(GLTransaction.amount), Decimal(0)).label("cost"),
    ).filter(GLTransaction.job_id == job_id)
    if as_of:
        nonlabor_q = nonlabor_q.filter(GLTransaction.txn_date <= as_of)
    nonlabor = nonlabor_q.one()

    # billing
    billing_q = db.query(
        func.coalesce(func.sum(JobBilling.amount_billed), Decimal(0)).label("billed"),
    ).filter(JobBilling.job_id == job_id)
    if as_of:
        billing_q = billing_q.filter(JobBilling.invoice_date <= as_of)
    billing = billing_q.one()

    actual_labor_hours = float(labor.hours)
    actual_labor_cost = float(labor.cost)
    actual_nonlabor_cost = float(nonlabor.cost)
    actual_total_cost = actual_labor_cost + actual_nonlabor_cost
    billed_to_date = float(billing.billed)

    planned_total_cost = None
    if budget:
        planned_total_cost = sum(
            float(v or 0)
            for v in [budget.planned_labor_cost, budget.planned_material_cost, budget.planned_sub_cost]
        )

    margin_to_date = None
    if billed_to_date > 0:
        margin_to_date = round((billed_to_date - actual_total_cost) / billed_to_date * 100, 2)

    labor_hours_variance = None
    if budget and budget.planned_labor_hours:
        labor_hours_variance = actual_labor_hours - float(budget.planned_labor_hours)

    return JobCostSummary(
        job_id=job.job_id,
        job_name=job.job_name,
        customer_name=job.customer_name,
        contract_value=float(job.contract_value) if job.contract_value else None,
        status=job.status.value,
        planned_labor_hours=float(budget.planned_labor_hours) if budget and budget.planned_labor_hours else None,
        planned_labor_cost=float(budget.planned_labor_cost) if budget and budget.planned_labor_cost else None,
        planned_material_cost=float(budget.planned_material_cost) if budget and budget.planned_material_cost else None,
        planned_sub_cost=float(budget.planned_sub_cost) if budget and budget.planned_sub_cost else None,
        planned_total_cost=planned_total_cost,
        actual_labor_hours=actual_labor_hours,
        actual_labor_cost=actual_labor_cost,
        actual_nonlabor_cost=actual_nonlabor_cost,
        actual_total_cost=actual_total_cost,
        billed_to_date=billed_to_date,
        margin_to_date=margin_to_date,
        labor_hours_variance=labor_hours_variance,
    )
