"""Seed the database with realistic demo data for client presentations.

Usage:
    python -m scripts.seed_demo_data          # uses DATABASE_URL from .env
    python -m scripts.seed_demo_data --reset   # drops and recreates all tables first

This creates a full demo dataset with:
- 8 jobs at various stages (active, near-complete, overrun, on-hold, closed)
- 15 employees across different trades and pay rates
- 12 cost codes covering common contractor work
- ~400 time entries spread across 8 weeks
- ~80 GL transactions (materials, subs, equipment, permits)
- Budgets for every job
- Billing records showing progress invoicing
- Burden rates (current + historical)
- Job mappings (ADP + QBO source keys)
- Exceptions (unmapped entries, overrun risks, margin drift)
- Daily metric snapshots for trend charts
"""

from __future__ import annotations

import random
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.database import Base, SessionLocal
from app.models.cost_code import CostCode
from app.models.employee import Employee
from app.models.exception import Exception as ExceptionModel
from app.models.exception import ExceptionSeverity, ExceptionType
from app.models.gl_transaction import GLTransaction, TransactionCategory
from app.models.job import Job, JobStatus
from app.models.job_billing import JobBilling
from app.models.job_budget import JobBudget
from app.models.job_daily_metric import JobDailyMetric
from app.models.job_mapping import JobMapping
from app.models.labor_burden_rate import LaborBurdenRate
from app.models.time_entry import TimeEntry

random.seed(42)  # reproducible demo data


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

COST_CODES = [
    ("DEMO", "Demolition"),
    ("FRAME", "Framing"),
    ("ROOF", "Roofing"),
    ("ELEC", "Electrical"),
    ("PLUMB", "Plumbing"),
    ("HVAC", "HVAC"),
    ("DRYWALL", "Drywall & Finishing"),
    ("PAINT", "Painting"),
    ("CONCRETE", "Concrete & Foundation"),
    ("SITE", "Site Work & Grading"),
    ("FACADE", "Facade / Exterior"),
    ("GEN", "General Conditions"),
]

EMPLOYEES = [
    ("EMP001", "Mike Torres", "Foreman", 62.00),
    ("EMP002", "Sarah Chen", "Project Manager", 72.00),
    ("EMP003", "James Wilson", "Electrician", 55.00),
    ("EMP004", "Maria Garcia", "Plumber", 52.00),
    ("EMP005", "Robert Johnson", "Carpenter", 48.00),
    ("EMP006", "David Kim", "Carpenter", 46.00),
    ("EMP007", "Lisa Brown", "Laborer", 32.00),
    ("EMP008", "Kevin O'Brien", "Laborer", 30.00),
    ("EMP009", "Angela Davis", "HVAC Tech", 58.00),
    ("EMP010", "Carlos Ramirez", "Roofer", 44.00),
    ("EMP011", "Tom Nguyen", "Roofer", 42.00),
    ("EMP012", "Rachel Scott", "Painter", 38.00),
    ("EMP013", "Marcus Hall", "Equipment Operator", 50.00),
    ("EMP014", "Jennifer Lee", "Superintendent", 68.00),
    ("EMP015", "Andre Thompson", "Apprentice", 24.00),
]

JOBS = [
    {
        "name": "325 Main St - Full Renovation",
        "ref": "PROJ-100",
        "customer": "Greenfield Properties LLC",
        "address": "325 Main St, Hartford CT 06103",
        "contract": 485000,
        "status": JobStatus.active,
        "start": date(2024, 9, 15),
        "end": date(2025, 3, 30),
        "retainage": 0.10,
        "budget_labor_hrs": 2800,
        "budget_labor_cost": 145000,
        "budget_material": 95000,
        "budget_sub": 120000,
        "progress": 0.55,  # how far along to simulate
        "billing_pct": 0.50,
        "margin_target": 0.26,
    },
    {
        "name": "Oak Ave Office Build-Out",
        "ref": "PROJ-200",
        "customer": "Summit Commercial Group",
        "address": "1200 Oak Ave, New Haven CT 06510",
        "contract": 320000,
        "status": JobStatus.active,
        "start": date(2024, 10, 1),
        "end": date(2025, 4, 15),
        "retainage": 0.10,
        "budget_labor_hrs": 1800,
        "budget_labor_cost": 95000,
        "budget_material": 65000,
        "budget_sub": 75000,
        "progress": 0.40,
        "billing_pct": 0.35,
        "margin_target": 0.27,
    },
    {
        "name": "Elm St Electrical Upgrade",
        "ref": "PROJ-300",
        "customer": "Elm Street Condo Association",
        "address": "45 Elm St, Stamford CT 06901",
        "contract": 128000,
        "status": JobStatus.active,
        "start": date(2024, 11, 1),
        "end": date(2025, 2, 28),
        "retainage": 0.05,
        "budget_labor_hrs": 650,
        "budget_labor_cost": 38000,
        "budget_material": 22000,
        "budget_sub": 35000,
        "progress": 0.85,
        "billing_pct": 0.75,
        "margin_target": 0.25,
    },
    {
        "name": "River Rd Roof Replacement",
        "ref": "PROJ-400",
        "customer": "Riverside Church",
        "address": "88 River Rd, Bridgeport CT 06604",
        "contract": 92000,
        "status": JobStatus.active,
        "start": date(2024, 12, 1),
        "end": date(2025, 2, 15),
        "retainage": 0.0,
        "budget_labor_hrs": 480,
        "budget_labor_cost": 24000,
        "budget_material": 32000,
        "budget_sub": 8000,
        "progress": 1.12,  # overrun!
        "billing_pct": 0.90,
        "margin_target": 0.30,
    },
    {
        "name": "Parkview Plaza Facade Restoration",
        "ref": "PROJ-500",
        "customer": "Parkview Management Corp",
        "address": "500 Park Ave, Norwalk CT 06850",
        "contract": 750000,
        "status": JobStatus.active,
        "start": date(2024, 8, 1),
        "end": date(2025, 6, 30),
        "retainage": 0.10,
        "budget_labor_hrs": 4200,
        "budget_labor_cost": 220000,
        "budget_material": 180000,
        "budget_sub": 150000,
        "progress": 0.35,
        "billing_pct": 0.30,
        "margin_target": 0.27,
    },
    {
        "name": "Willow Creek Townhomes - Phase 1",
        "ref": "PROJ-600",
        "customer": "Willow Creek Development",
        "address": "Willow Creek Rd, Danbury CT 06810",
        "contract": 1200000,
        "status": JobStatus.active,
        "start": date(2024, 7, 15),
        "end": date(2025, 8, 30),
        "retainage": 0.10,
        "budget_labor_hrs": 6500,
        "budget_labor_cost": 340000,
        "budget_material": 280000,
        "budget_sub": 250000,
        "progress": 0.45,
        "billing_pct": 0.42,
        "margin_target": 0.28,
    },
    {
        "name": "Harbor View HVAC Retrofit",
        "ref": "PROJ-700",
        "customer": "Harbor View Hotel",
        "address": "12 Harbor St, Mystic CT 06355",
        "contract": 175000,
        "status": JobStatus.on_hold,
        "start": date(2024, 11, 15),
        "end": None,
        "retainage": 0.05,
        "budget_labor_hrs": 900,
        "budget_labor_cost": 55000,
        "budget_material": 45000,
        "budget_sub": 30000,
        "progress": 0.15,
        "billing_pct": 0.10,
        "margin_target": 0.25,
    },
    {
        "name": "Cedar Lane Kitchen Remodel",
        "ref": "PROJ-800",
        "customer": "The Johnsons (Residential)",
        "address": "22 Cedar Lane, Westport CT 06880",
        "contract": 68000,
        "status": JobStatus.closed,
        "start": date(2024, 6, 1),
        "end": date(2024, 9, 15),
        "retainage": 0.0,
        "budget_labor_hrs": 350,
        "budget_labor_cost": 18000,
        "budget_material": 22000,
        "budget_sub": 12000,
        "progress": 1.0,
        "billing_pct": 1.0,
        "margin_target": 0.30,
    },
]

VENDORS = {
    TransactionCategory.materials: [
        "ABC Supply Co",
        "HD Supply",
        "Beacon Building Products",
        "Ferguson Enterprises",
        "Fastenal",
        "84 Lumber",
    ],
    TransactionCategory.sub: [
        "Northeast Electric LLC",
        "Hartford Plumbing Co",
        "Precision HVAC Services",
        "Metro Framing Contractors",
        "Bay State Masonry",
    ],
    TransactionCategory.equipment: [
        "United Rentals",
        "Sunbelt Rentals",
        "Herc Equipment",
    ],
    TransactionCategory.permit: [
        "City of Hartford Permits",
        "Town of Stamford Building Dept",
        "State of CT DPUC",
    ],
}


def _random_date_between(start: date, end: date) -> date:
    delta = (end - start).days
    if delta <= 0:
        return start
    return start + timedelta(days=random.randint(0, delta))


def _workdays_in_range(start: date, end: date) -> list[date]:
    """Return list of weekday dates between start and end."""
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            days.append(current)
        current += timedelta(days=1)
    return days


def seed(db: Session, reset: bool = False) -> dict:
    """Populate database with demo data. Returns summary counts."""
    bind = db.get_bind()
    if reset:
        Base.metadata.drop_all(bind=bind)
        Base.metadata.create_all(bind=bind)
    else:
        Base.metadata.create_all(bind=bind)

    counts = {}

    # --- Burden rates (historical + current) ---
    burden_old = LaborBurdenRate(
        effective_date=date(2024, 1, 1),
        fica_pct=Decimal("0.0765"),
        futa_pct=Decimal("0.0060"),
        suta_pct=Decimal("0.0320"),
        workers_comp_pct=Decimal("0.0480"),
        benefits_per_hour=Decimal("4.50"),
        overhead_multiplier=Decimal("0.0000"),
    )
    burden_current = LaborBurdenRate(
        effective_date=date(2024, 7, 1),
        fica_pct=Decimal("0.0765"),
        futa_pct=Decimal("0.0060"),
        suta_pct=Decimal("0.0290"),
        workers_comp_pct=Decimal("0.0520"),
        benefits_per_hour=Decimal("5.25"),
        overhead_multiplier=Decimal("0.0000"),
    )
    db.add_all([burden_old, burden_current])
    db.flush()
    counts["burden_rates"] = 2

    # Use the current burden for cost computations
    pct_sum = float(
        burden_current.fica_pct
        + burden_current.futa_pct
        + burden_current.suta_pct
        + burden_current.workers_comp_pct
    )
    burden_mult = 1.0 + pct_sum
    benefits_hr = float(burden_current.benefits_per_hour)

    # --- Cost codes ---
    cc_map = {}
    for code, name in COST_CODES:
        cc = CostCode(code=code, name=name)
        db.add(cc)
        db.flush()
        cc_map[code] = cc.cost_code_id
    counts["cost_codes"] = len(COST_CODES)

    # --- Employees ---
    emp_map = {}
    for ref, name, role, rate in EMPLOYEES:
        emp = Employee(adp_employee_ref=ref, name=name, role=role)
        db.add(emp)
        db.flush()
        emp_map[ref] = (emp.employee_id, rate)
    counts["employees"] = len(EMPLOYEES)

    # --- Jobs + budgets + mappings ---
    job_objs = {}
    for j in JOBS:
        job = Job(
            external_job_ref=j["ref"],
            job_name=j["name"],
            customer_name=j["customer"],
            site_address=j["address"],
            start_date=j["start"],
            end_date=j["end"],
            contract_value=Decimal(str(j["contract"])),
            retainage_pct=Decimal(str(j["retainage"])),
            status=j["status"],
        )
        db.add(job)
        db.flush()
        job_objs[j["ref"]] = (job.job_id, j)

        # Budget
        budget = JobBudget(
            job_id=job.job_id,
            budget_version=1,
            planned_revenue=Decimal(str(j["contract"])),
            planned_labor_hours=Decimal(str(j["budget_labor_hrs"])),
            planned_labor_cost=Decimal(str(j["budget_labor_cost"])),
            planned_material_cost=Decimal(str(j["budget_material"])),
            planned_sub_cost=Decimal(str(j["budget_sub"])),
        )
        db.add(budget)

        # Mappings (ADP + QBO)
        db.add(
            JobMapping(
                source_system="adp",
                source_key=j["ref"],
                job_id=job.job_id,
                confidence=Decimal("1.00"),
                created_by="system",
                notes="Auto-seeded demo mapping",
            )
        )
        db.add(
            JobMapping(
                source_system="qbo",
                source_key=j["ref"],
                job_id=job.job_id,
                confidence=Decimal("1.00"),
                created_by="system",
                notes="Auto-seeded demo mapping",
            )
        )

    counts["jobs"] = len(JOBS)
    counts["budgets"] = len(JOBS)
    counts["mappings"] = len(JOBS) * 2

    # --- Unmapped source keys (for exception demos) ---
    db.add(
        JobMapping(
            source_system="adp",
            source_key="OVERHEAD",
            job_id=None,
            confidence=Decimal("0.00"),
            created_by="system",
            notes="Unmapped - overhead/shop time",
        )
    )
    db.add(
        JobMapping(
            source_system="qbo",
            source_key="MISC-VENDOR",
            job_id=None,
            confidence=Decimal("0.00"),
            created_by="system",
            notes="Unmapped - unknown vendor charges",
        )
    )
    counts["mappings"] += 2

    db.flush()

    # --- Time entries ---
    # Assign employees to jobs with weighted allocation
    job_crews = {
        "PROJ-100": ["EMP001", "EMP005", "EMP006", "EMP007", "EMP012", "EMP015"],
        "PROJ-200": ["EMP002", "EMP005", "EMP006", "EMP008", "EMP012"],
        "PROJ-300": ["EMP003", "EMP007", "EMP015"],
        "PROJ-400": ["EMP010", "EMP011", "EMP008"],
        "PROJ-500": ["EMP001", "EMP014", "EMP005", "EMP006", "EMP007", "EMP008", "EMP013"],
        "PROJ-600": ["EMP002", "EMP014", "EMP003", "EMP004", "EMP005", "EMP006", "EMP009", "EMP013"],
        "PROJ-700": ["EMP009", "EMP008"],
        "PROJ-800": ["EMP004", "EMP005", "EMP012"],
    }

    # Cost codes typical for each job type
    job_cost_codes = {
        "PROJ-100": ["DEMO", "FRAME", "ELEC", "PLUMB", "DRYWALL", "PAINT", "GEN"],
        "PROJ-200": ["DEMO", "FRAME", "ELEC", "PLUMB", "HVAC", "DRYWALL", "PAINT"],
        "PROJ-300": ["ELEC", "GEN"],
        "PROJ-400": ["ROOF", "GEN"],
        "PROJ-500": ["DEMO", "FACADE", "CONCRETE", "GEN"],
        "PROJ-600": ["SITE", "CONCRETE", "FRAME", "ROOF", "ELEC", "PLUMB", "HVAC", "GEN"],
        "PROJ-700": ["HVAC", "ELEC", "GEN"],
        "PROJ-800": ["DEMO", "PLUMB", "ELEC", "DRYWALL", "PAINT"],
    }

    time_entry_count = 0
    now = date.today()

    for proj_ref, (job_id, jdata) in job_objs.items():
        crew = job_crews.get(proj_ref, [])
        codes = job_cost_codes.get(proj_ref, ["GEN"])
        progress = jdata["progress"]

        job_start = jdata["start"]
        job_end_target = jdata["end"] or now
        # Simulate progress up to progress * duration
        duration_days = (job_end_target - job_start).days
        sim_end = min(
            job_start + timedelta(days=int(duration_days * min(progress, 1.0))),
            now,
        )

        workdays = _workdays_in_range(job_start, sim_end)
        if not workdays:
            continue

        target_hours = float(jdata["budget_labor_hrs"]) * progress

        # Distribute hours across workdays and crew
        hours_per_day_per_person = target_hours / max(len(workdays) * len(crew), 1)

        for wd in workdays:
            for emp_ref in crew:
                # Some randomness: not everyone works every day
                if random.random() < 0.75:
                    emp_id, pay_rate = emp_map[emp_ref]
                    hrs = round(
                        random.gauss(hours_per_day_per_person, hours_per_day_per_person * 0.25),
                        1,
                    )
                    hrs = max(2.0, min(12.0, hrs))  # clamp

                    cost_code = random.choice(codes)
                    direct = round(hrs * pay_rate, 2)
                    burdened = round(direct * burden_mult + benefits_hr * hrs, 2)

                    db.add(
                        TimeEntry(
                            job_id=job_id,
                            employee_id=emp_id,
                            work_date=wd,
                            hours=Decimal(str(hrs)),
                            pay_rate=Decimal(str(pay_rate)),
                            cost_code_id=cc_map.get(cost_code),
                            labor_cost_direct=Decimal(str(direct)),
                            labor_cost_burdened=Decimal(str(burdened)),
                            raw_source_id=f"adp:demo:{time_entry_count}",
                        )
                    )
                    time_entry_count += 1

    # Add some unmapped time entries (no job_id)
    for i in range(15):
        emp_ref = random.choice(list(emp_map.keys()))
        emp_id, pay_rate = emp_map[emp_ref]
        wd = _random_date_between(date(2024, 10, 1), now)
        hrs = round(random.uniform(2, 8), 1)
        direct = round(hrs * pay_rate, 2)
        burdened = round(direct * burden_mult + benefits_hr * hrs, 2)
        db.add(
            TimeEntry(
                job_id=None,
                employee_id=emp_id,
                work_date=wd,
                hours=Decimal(str(hrs)),
                pay_rate=Decimal(str(pay_rate)),
                labor_cost_direct=Decimal(str(direct)),
                labor_cost_burdened=Decimal(str(burdened)),
                raw_source_id=f"adp:demo:unmapped:{i}",
            )
        )
        time_entry_count += 1

    counts["time_entries"] = time_entry_count
    db.flush()

    # --- GL Transactions ---
    txn_count = 0

    for proj_ref, (job_id, jdata) in job_objs.items():
        progress = jdata["progress"]
        job_start = jdata["start"]

        # Materials
        material_budget = jdata["budget_material"]
        material_spend = material_budget * progress * random.uniform(0.85, 1.15)
        n_material_txns = random.randint(3, 10)
        for _ in range(n_material_txns):
            amount = round(material_spend / n_material_txns * random.uniform(0.5, 1.5), 2)
            vendor = random.choice(VENDORS[TransactionCategory.materials])
            txn_date = _random_date_between(job_start, min(now, jdata["end"] or now))
            db.add(
                GLTransaction(
                    job_id=job_id,
                    txn_date=txn_date,
                    vendor=vendor,
                    category=TransactionCategory.materials,
                    amount=Decimal(str(amount)),
                    cost_code_id=cc_map.get(random.choice(["FRAME", "ELEC", "PLUMB", "ROOF", "CONCRETE", "FACADE"])),
                    description=f"Materials delivery - {vendor}",
                    raw_source_id=f"qbo:demo:{txn_count}",
                )
            )
            txn_count += 1

        # Subcontractors
        sub_budget = jdata["budget_sub"]
        sub_spend = sub_budget * progress * random.uniform(0.80, 1.10)
        n_sub_txns = random.randint(2, 6)
        for _ in range(n_sub_txns):
            amount = round(sub_spend / n_sub_txns * random.uniform(0.6, 1.4), 2)
            vendor = random.choice(VENDORS[TransactionCategory.sub])
            txn_date = _random_date_between(job_start, min(now, jdata["end"] or now))
            db.add(
                GLTransaction(
                    job_id=job_id,
                    txn_date=txn_date,
                    vendor=vendor,
                    category=TransactionCategory.sub,
                    amount=Decimal(str(amount)),
                    description=f"Subcontract payment - {vendor}",
                    raw_source_id=f"qbo:demo:{txn_count}",
                )
            )
            txn_count += 1

        # Equipment rentals (some jobs)
        if random.random() < 0.6:
            for _ in range(random.randint(1, 3)):
                vendor = random.choice(VENDORS[TransactionCategory.equipment])
                amount = round(random.uniform(800, 4500), 2)
                txn_date = _random_date_between(job_start, min(now, jdata["end"] or now))
                db.add(
                    GLTransaction(
                        job_id=job_id,
                        txn_date=txn_date,
                        vendor=vendor,
                        category=TransactionCategory.equipment,
                        amount=Decimal(str(amount)),
                        description=f"Equipment rental - {vendor}",
                        raw_source_id=f"qbo:demo:{txn_count}",
                    )
                )
                txn_count += 1

        # Permits
        for _ in range(random.randint(1, 2)):
            vendor = random.choice(VENDORS[TransactionCategory.permit])
            amount = round(random.uniform(250, 1800), 2)
            db.add(
                GLTransaction(
                    job_id=job_id,
                    txn_date=job_start + timedelta(days=random.randint(0, 14)),
                    vendor=vendor,
                    category=TransactionCategory.permit,
                    amount=Decimal(str(amount)),
                    description=f"Building/trade permit - {vendor}",
                    raw_source_id=f"qbo:demo:{txn_count}",
                )
            )
            txn_count += 1

    # Unmapped GL transactions
    for i in range(8):
        vendor = random.choice(["Unknown Supplier", "Cash Purchase", "Petty Cash", "Misc Vendor"])
        amount = round(random.uniform(100, 3000), 2)
        txn_date = _random_date_between(date(2024, 10, 1), now)
        db.add(
            GLTransaction(
                job_id=None,
                txn_date=txn_date,
                vendor=vendor,
                category=TransactionCategory.other,
                amount=Decimal(str(amount)),
                description="Unmapped expense - needs job assignment",
                raw_source_id=f"qbo:demo:unmapped:{i}",
            )
        )
        txn_count += 1

    counts["gl_transactions"] = txn_count
    db.flush()

    # --- Billing ---
    billing_count = 0
    for proj_ref, (job_id, jdata) in job_objs.items():
        billing_pct = jdata["billing_pct"]
        contract = jdata["contract"]
        retainage = jdata["retainage"]
        total_billed = contract * billing_pct

        # Split into monthly progress billings
        job_start = jdata["start"]
        n_invoices = max(1, int(billing_pct * 6))  # ~monthly
        for inv_idx in range(n_invoices):
            inv_amount = round(total_billed / n_invoices * random.uniform(0.8, 1.2), 2)
            inv_date = job_start + timedelta(days=30 * (inv_idx + 1))
            if inv_date > now:
                inv_date = now - timedelta(days=random.randint(1, 14))

            retainage_held = round(inv_amount * retainage, 2) if retainage else None
            collected = round(inv_amount * random.uniform(0.85, 1.0), 2) if inv_idx < n_invoices - 1 else None

            db.add(
                JobBilling(
                    job_id=job_id,
                    invoice_date=inv_date,
                    amount_billed=Decimal(str(inv_amount)),
                    amount_collected=Decimal(str(collected)) if collected else None,
                    retainage_held=Decimal(str(retainage_held)) if retainage_held else None,
                    raw_source_id=f"billing:demo:{billing_count}",
                )
            )
            billing_count += 1

    counts["billing_records"] = billing_count
    db.flush()

    # --- Exceptions ---
    exc_count = 0

    # Unmapped time entries
    db.add(
        ExceptionModel(
            type=ExceptionType.UNMAPPED_TIME_ENTRY,
            severity=ExceptionSeverity.warn,
            message="15 ADP time entries have no job mapping (source: OVERHEAD). Total: 82.5 hours.",
            source_ref="adp:OVERHEAD",
            created_at=datetime(2024, 12, 15, 9, 30),
        )
    )
    exc_count += 1

    # Unmapped transactions
    db.add(
        ExceptionModel(
            type=ExceptionType.UNMAPPED_TRANSACTION,
            severity=ExceptionSeverity.warn,
            message="8 QBO transactions totaling $7,234.00 have no job mapping.",
            source_ref="qbo:MISC-VENDOR",
            created_at=datetime(2024, 12, 18, 14, 15),
        )
    )
    exc_count += 1

    # Job overrun (PROJ-400 is over budget)
    proj400_id = job_objs["PROJ-400"][0]
    db.add(
        ExceptionModel(
            job_id=proj400_id,
            type=ExceptionType.JOB_OVERRUN_RISK,
            severity=ExceptionSeverity.critical,
            message="River Rd Roof Replacement is at 112% of budget. Labor hours exceeded plan by 54 hours. Immediate review needed.",
            created_at=datetime(2025, 1, 20, 8, 0),
        )
    )
    exc_count += 1

    # Margin drift on PROJ-500
    proj500_id = job_objs["PROJ-500"][0]
    db.add(
        ExceptionModel(
            job_id=proj500_id,
            type=ExceptionType.MARGIN_DRIFT,
            severity=ExceptionSeverity.warn,
            message="Parkview Plaza Facade: current margin is 19.2%, target is 27%. Material costs running 15% above estimate.",
            created_at=datetime(2025, 1, 25, 11, 0),
        )
    )
    exc_count += 1

    # Data integrity
    db.add(
        ExceptionModel(
            type=ExceptionType.DATA_INTEGRITY,
            severity=ExceptionSeverity.info,
            message="3 duplicate time entries detected in ADP import from 2025-01-15. Deduplication applied.",
            source_ref="adp:dedup:20250115",
            created_at=datetime(2025, 1, 15, 16, 0),
            resolved_at=datetime(2025, 1, 15, 16, 5),
        )
    )
    exc_count += 1

    # Labor burn rate warning
    proj100_id = job_objs["PROJ-100"][0]
    db.add(
        ExceptionModel(
            job_id=proj100_id,
            type=ExceptionType.JOB_OVERRUN_RISK,
            severity=ExceptionSeverity.warn,
            message="325 Main St: labor hours at 55% of budget but only 48% of timeline elapsed. Burn rate trending 15% above plan.",
            created_at=datetime(2025, 1, 28, 9, 0),
        )
    )
    exc_count += 1

    counts["exceptions"] = exc_count
    db.flush()

    # --- Daily metrics (for trend charts) ---
    metric_count = 0
    for proj_ref, (job_id, jdata) in job_objs.items():
        job_start = jdata["start"]
        sim_end = min(now, jdata["end"] or now)
        budget_total = jdata["budget_labor_cost"] + jdata["budget_material"] + jdata["budget_sub"]

        # Build cumulative daily snapshots
        cum_hours = 0.0
        cum_labor = 0.0
        cum_nonlabor = 0.0
        cum_billed = 0.0

        # Generate weekly snapshots (every Friday)
        current = job_start
        while current <= sim_end:
            # Skip to next Friday
            days_until_friday = (4 - current.weekday()) % 7
            if days_until_friday == 0 and current != job_start:
                days_until_friday = 7
            current = current + timedelta(days=days_until_friday)
            if current > sim_end:
                break

            elapsed_pct = (current - job_start).days / max((sim_end - job_start).days, 1)
            progress_at_date = jdata["progress"] * elapsed_pct

            target_total = budget_total * progress_at_date
            labor_share = jdata["budget_labor_cost"] / budget_total
            nonlabor_share = 1.0 - labor_share

            cum_hours = jdata["budget_labor_hrs"] * progress_at_date * random.uniform(0.9, 1.1)
            cum_labor = target_total * labor_share * random.uniform(0.92, 1.08)
            cum_nonlabor = target_total * nonlabor_share * random.uniform(0.88, 1.12)
            cum_total = cum_labor + cum_nonlabor
            cum_billed = jdata["contract"] * jdata["billing_pct"] * elapsed_pct

            pct_complete = cum_total / budget_total if budget_total > 0 else None
            crew_size = len(job_crews.get(proj_ref, [])) if jdata["status"] != JobStatus.on_hold else 0

            db.add(
                JobDailyMetric(
                    job_id=job_id,
                    date=current,
                    hours=Decimal(str(round(cum_hours, 2))),
                    labor_cost=Decimal(str(round(cum_labor, 2))),
                    nonlabor_cost=Decimal(str(round(cum_nonlabor, 2))),
                    total_cost=Decimal(str(round(cum_total, 2))),
                    billed_to_date=Decimal(str(round(cum_billed, 2))),
                    pct_complete=Decimal(str(round(pct_complete, 4))) if pct_complete else None,
                    crew_size_estimate=crew_size,
                )
            )
            metric_count += 1

    counts["daily_metrics"] = metric_count

    db.commit()
    return counts


def main():
    reset = "--reset" in sys.argv
    db = SessionLocal()
    try:
        print("Seeding demo data..." + (" (with reset)" if reset else ""))
        counts = seed(db, reset=reset)
        print("\nDemo data seeded successfully!")
        print("-" * 40)
        for key, val in counts.items():
            print(f"  {key:20s}: {val}")
        print("-" * 40)
        print("\nYou can now:")
        print("  - Hit the API at http://localhost:8000/docs")
        print("  - Open Metabase at http://localhost:3000")
        print("  - Try: GET /jobs, GET /wip, GET /exceptions")
    finally:
        db.close()


if __name__ == "__main__":
    main()
