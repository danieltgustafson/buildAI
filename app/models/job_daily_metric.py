from typing import Optional


import uuid

from sqlalchemy import Date, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
class JobDailyMetric(Base):
    __tablename__ = "job_daily_metrics"
    __table_args__ = (UniqueConstraint("job_id", "date", name="uq_job_daily_metric"),)

    metric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=False
    )
    date: Mapped[str] = mapped_column(Date, nullable=False)
    hours: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    labor_cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    nonlabor_cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total_cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    billed_to_date: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    pct_complete: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    crew_size_estimate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    job = relationship("Job", back_populates="daily_metrics")
