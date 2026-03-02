"""Tests for CSV ingestion services."""

from datetime import date

from app.models.job import Job, JobStatus
from app.models.job_mapping import JobMapping
from app.models.labor_burden_rate import LaborBurdenRate
from app.models.time_entry import TimeEntry
from app.models.gl_transaction import GLTransaction
from app.services.ingest_adp import ingest_adp_csv
from app.services.ingest_qbo import ingest_qbo_csv

SAMPLE_ADP_CSV = b"""employee_id,employee_name,work_date,hours,pay_rate,job,gross_pay
EMP001,John Smith,2024-01-15,8.0,45.00,PROJ-100,360.00
EMP002,Jane Doe,2024-01-15,8.0,52.00,PROJ-100,416.00
EMP003,Bob Wilson,2024-01-15,10.0,38.00,UNMAPPED,380.00
"""

SAMPLE_QBO_CSV = b"""date,vendor,amount,category,customer,memo
2024-01-10,ABC Supply Co,5250.00,Materials,PROJ-100,Roofing materials
2024-01-12,XYZ Subs Inc,12000.00,Subcontractor,UNMAPPED-QBO,Framing sub
"""


def test_ingest_adp_with_mapping(db):
    # Setup: create a job and a mapping
    job = Job(job_name="Main St Reno", status=JobStatus.active)
    db.add(job)
    db.flush()

    db.add(JobMapping(source_system="adp", source_key="PROJ-100", job_id=job.job_id))
    db.add(
        LaborBurdenRate(
            effective_date=date(2024, 1, 1),
            fica_pct=0.0765,
            futa_pct=0.006,
            suta_pct=0.03,
            workers_comp_pct=0.05,
        )
    )
    db.commit()

    result = ingest_adp_csv(db, SAMPLE_ADP_CSV, "test_adp.csv")
    assert result.rows_ingested == 3
    assert result.rows_mapped == 2  # PROJ-100 entries
    assert result.rows_unmapped == 1  # UNMAPPED entry

    # Check time entries exist
    entries = db.query(TimeEntry).all()
    assert len(entries) == 3

    # Mapped entries should have job_id
    mapped = [e for e in entries if e.job_id is not None]
    assert len(mapped) == 2

    # Burdened cost should be computed
    for entry in entries:
        assert entry.labor_cost_burdened is not None
        assert float(entry.labor_cost_burdened) > 0


def test_ingest_qbo_with_mapping(db):
    job = Job(job_name="Main St Reno", status=JobStatus.active)
    db.add(job)
    db.flush()

    db.add(JobMapping(source_system="qbo", source_key="PROJ-100", job_id=job.job_id))
    db.commit()

    result = ingest_qbo_csv(db, SAMPLE_QBO_CSV, "test_qbo.csv")
    assert result.rows_ingested == 2
    assert result.rows_mapped == 1
    assert result.rows_unmapped == 1

    txns = db.query(GLTransaction).all()
    assert len(txns) == 2
