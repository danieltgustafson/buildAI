"""Tests for the cost engine: burdened labor and job cost rollups."""

import uuid
from datetime import date

from app.models.gl_transaction import GLTransaction, TransactionCategory
from app.models.job import Job, JobStatus
from app.models.job_billing import JobBilling
from app.models.job_budget import JobBudget
from app.models.labor_burden_rate import LaborBurdenRate
from app.models.time_entry import TimeEntry
from app.services.cost_engine import compute_burdened_cost, job_cost_summary


def _make_burden_rate():
    return LaborBurdenRate(
        effective_date=date(2024, 1, 1),
        fica_pct=0.0765,
        futa_pct=0.006,
        suta_pct=0.03,
        workers_comp_pct=0.05,
        benefits_per_hour=5.0,
        overhead_multiplier=0.0,
    )


def test_compute_burdened_cost_from_pay_rate():
    burden = _make_burden_rate()
    dc, bc = compute_burdened_cost(hours=8.0, pay_rate=50.0, direct_cost=None, burden=burden)
    assert dc == 400.0
    # burden_multiplier = 1 + 0.0765 + 0.006 + 0.03 + 0.05 = 1.1625
    # burdened = 400 * 1.1625 + 5.0 * 8 = 465.0 + 40.0 = 505.0
    assert bc == 505.0


def test_compute_burdened_cost_from_direct_cost():
    burden = _make_burden_rate()
    dc, bc = compute_burdened_cost(hours=8.0, pay_rate=None, direct_cost=400.0, burden=burden)
    assert dc == 400.0
    assert bc == 505.0


def test_compute_burdened_cost_no_burden():
    dc, bc = compute_burdened_cost(hours=8.0, pay_rate=50.0, direct_cost=None, burden=None)
    assert dc == 400.0
    assert bc == 400.0  # no burden applied


def test_job_cost_summary_basic(db):
    # Create a job
    job = Job(job_name="Test Job", status=JobStatus.active, contract_value=100000)
    db.add(job)
    db.flush()

    # Add budget
    budget = JobBudget(
        job_id=job.job_id,
        budget_version=1,
        planned_labor_hours=100,
        planned_labor_cost=5000,
        planned_material_cost=3000,
        planned_sub_cost=2000,
    )
    db.add(budget)

    # Add time entries
    for i in range(5):
        db.add(
            TimeEntry(
                job_id=job.job_id,
                work_date=date(2024, 1, 15 + i),
                hours=8,
                labor_cost_burdened=500,
            )
        )

    # Add GL transactions
    db.add(
        GLTransaction(
            job_id=job.job_id,
            txn_date=date(2024, 1, 15),
            category=TransactionCategory.materials,
            amount=1500,
        )
    )

    # Add billing
    db.add(
        JobBilling(
            job_id=job.job_id,
            invoice_date=date(2024, 1, 20),
            amount_billed=5000,
        )
    )

    db.commit()

    summary = job_cost_summary(db, job.job_id)
    assert summary.actual_labor_hours == 40
    assert summary.actual_labor_cost == 2500
    assert summary.actual_nonlabor_cost == 1500
    assert summary.actual_total_cost == 4000
    assert summary.billed_to_date == 5000
    assert summary.planned_labor_hours == 100
    assert summary.planned_total_cost == 10000
    assert summary.margin_to_date is not None
    # margin = (5000 - 4000) / 5000 * 100 = 20.0
    assert summary.margin_to_date == 20.0
