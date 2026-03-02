"""Tests for the WIP engine."""

from datetime import date

from app.models.gl_transaction import GLTransaction, TransactionCategory
from app.models.job import Job, JobStatus
from app.models.job_billing import JobBilling
from app.models.job_budget import JobBudget
from app.models.time_entry import TimeEntry
from app.services.wip_engine import wip_for_job


def test_wip_basic(db):
    job = Job(
        job_name="WIP Test Job",
        status=JobStatus.active,
        contract_value=100000,
    )
    db.add(job)
    db.flush()

    # Budget: total planned cost = 5000 + 3000 + 2000 = 10000
    db.add(
        JobBudget(
            job_id=job.job_id,
            budget_version=1,
            planned_labor_hours=100,
            planned_labor_cost=5000,
            planned_material_cost=3000,
            planned_sub_cost=2000,
        )
    )

    # Actual cost = 2500 (labor) + 1500 (materials) = 4000
    for i in range(5):
        db.add(
            TimeEntry(
                job_id=job.job_id,
                work_date=date(2024, 1, 15 + i),
                hours=8,
                labor_cost_burdened=500,
            )
        )
    db.add(
        GLTransaction(
            job_id=job.job_id,
            txn_date=date(2024, 1, 15),
            category=TransactionCategory.materials,
            amount=1500,
        )
    )

    # Billed 5000
    db.add(
        JobBilling(
            job_id=job.job_id,
            invoice_date=date(2024, 1, 20),
            amount_billed=5000,
        )
    )
    db.commit()

    report = wip_for_job(db, job.job_id)
    assert report.actual_total_cost == 4000
    assert report.budget_total_cost == 10000
    # pct_complete = 4000 / 10000 = 0.4
    assert report.pct_complete == 0.4
    # earned_revenue = 0.4 * 100000 = 40000
    assert report.earned_revenue == 40000.0
    # over_under = 5000 - 40000 = -35000 (under-billed)
    assert report.over_under_billing == -35000.0
    assert "JOB_OVERRUN_RISK" not in report.flags


def test_wip_overrun_flag(db):
    job = Job(
        job_name="Overrun Job",
        status=JobStatus.active,
        contract_value=50000,
    )
    db.add(job)
    db.flush()

    # Budget: total = 1000
    db.add(
        JobBudget(
            job_id=job.job_id,
            budget_version=1,
            planned_labor_hours=10,
            planned_labor_cost=500,
            planned_material_cost=300,
            planned_sub_cost=200,
        )
    )

    # Actual cost = 1200 (exceeds budget of 1000)
    db.add(
        TimeEntry(
            job_id=job.job_id,
            work_date=date(2024, 1, 15),
            hours=20,
            labor_cost_burdened=1200,
        )
    )
    db.commit()

    report = wip_for_job(db, job.job_id)
    assert report.pct_complete == 1.2  # capped at 1.2
    assert "JOB_OVERRUN_RISK" in report.flags
