from typing import Optional


import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
class JobBudget(Base):
    __tablename__ = "job_budgets"

    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=False
    )
    budget_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    planned_revenue: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    planned_labor_hours: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    planned_labor_cost: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    planned_material_cost: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    planned_sub_cost: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    job = relationship("Job", back_populates="budgets")
