"""Proportional crew scheduling algorithm.

For each working day in the month:
  - Rank active jobs by how much of their monthly demand is still unmet
  - Assign each available crew member to the job with the highest unmet demand
  - Decrement that job's remaining need by 1

Result: crew naturally concentrates on bigger / more behind-schedule jobs.
Days where total demand < available crew → some people go unassigned (idle).
Days where demand > crew → demand partially unmet (understaffed signal).
"""

from __future__ import annotations

import random
from calendar import monthrange
from datetime import date

from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.job_labor_demand import JobLaborDemand
from app.models.schedule_assignment import ScheduleAssignment


def generate_schedule(
    month: str,
    absent_employee_ids: set[str],
    db: Session,
    clear_existing: bool = True,
) -> dict:
    year, mo = int(month[:4]), int(month[5:])
    _, days_in_month = monthrange(year, mo)

    working_days = [
        date(year, mo, d)
        for d in range(1, days_in_month + 1)
        if date(year, mo, d).weekday() < 5  # Mon–Fri
    ]

    start, end = date(year, mo, 1), date(year, mo, days_in_month)

    if clear_existing:
        db.query(ScheduleAssignment).filter(
            ScheduleAssignment.work_date >= start,
            ScheduleAssignment.work_date <= end,
        ).delete(synchronize_session=False)
        db.flush()

    # Aggregate demand per job for this month (sum across crew types)
    demands = db.query(JobLaborDemand).filter_by(year_month=month).all()
    if not demands:
        return {
            "error": f"No demand data found for {month}. "
                     "Import the workbook first, or add demand manually."
        }

    job_remaining: dict[str, float] = {}  # str(job_id) -> remaining man-days
    job_lookup: dict[str, object] = {}    # str(job_id) -> Job ORM object

    for d in demands:
        key = str(d.job_id)
        job_remaining[key] = job_remaining.get(key, 0) + float(d.man_days_needed)
        job_lookup[key] = d.job

    total_demand = sum(job_remaining.values())

    # Available crew — sorted by ranking score descending so higher-ranked
    # workers get first pick of the most demanding jobs each day.
    all_employees = db.query(Employee).all()
    crew = sorted(
        [e for e in all_employees if str(e.employee_id) not in absent_employee_ids],
        key=lambda e: (e.ranking_score or 0),
        reverse=True,
    )

    total_supply = len(crew) * len(working_days)
    assignments_created = 0

    for work_date in working_days:
        # Jobs still needing people today
        active = [(jid, rem) for jid, rem in job_remaining.items() if rem > 0]
        if not active:
            break  # all demand satisfied

        # Shuffle crew slightly so the same person isn't always first pick
        day_crew = list(crew)
        random.shuffle(day_crew)

        for emp in day_crew:
            if not active:
                break

            # Assign to the job with the most remaining demand
            active.sort(key=lambda x: x[1], reverse=True)
            best_job_id, _ = active[0]

            db.add(ScheduleAssignment(
                employee_id=emp.employee_id,
                job_id=job_lookup[best_job_id].job_id,
                work_date=work_date,
            ))
            assignments_created += 1

            job_remaining[best_job_id] -= 1
            # Rebuild active list with updated remaining
            active = [(jid, job_remaining[jid]) for jid, _ in active if job_remaining[jid] > 0]

    db.commit()

    unmet = sum(max(0.0, v) for v in job_remaining.values())
    return {
        "month": month,
        "working_days": len(working_days),
        "available_crew": len(crew),
        "total_supply_days": total_supply,
        "total_demand_days": round(total_demand),
        "assignments_created": assignments_created,
        "demand_unmet_days": round(unmet),
        "demand_met_pct": round((total_demand - unmet) / total_demand * 100, 1) if total_demand else 0,
        "crew_utilization_pct": round(assignments_created / total_supply * 100, 1) if total_supply else 0,
    }
