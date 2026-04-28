from typing import Optional
import uuid

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobLaborDemand(Base):
    __tablename__ = "job_labor_demand"
    __table_args__ = (
        UniqueConstraint("job_id", "year_month", "crew_type", name="uq_job_labor_demand"),
    )

    demand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=False
    )
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    crew_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    man_days_needed: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0)

    job = relationship("Job", backref="labor_demands")
