from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class WIPReport(BaseModel):
    job_id: UUID
    job_name: str
    customer_name: str | None = None
    contract_value: float | None = None

    actual_total_cost: float = 0
    budget_total_cost: float | None = None
    pct_complete: float | None = None
    earned_revenue: float | None = None
    billed_to_date: float = 0
    over_under_billing: float | None = None

    status: str
    flags: list[str] = []
