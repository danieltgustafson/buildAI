from typing import Optional


import enum
import uuid

from sqlalchemy import Date, Enum, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
class JobStatus(str, enum.Enum):
    active = "active"
    closed = "closed"
    on_hold = "on_hold"
class Job(Base):
    __tablename__ = "jobs"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    external_job_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    site_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_date: Mapped[Optional[str]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(Date, nullable=True)
    contract_value: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    retainage_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), nullable=False, default=JobStatus.active
    )

    # relationships
    time_entries = relationship("TimeEntry", back_populates="job", lazy="dynamic")
    gl_transactions = relationship("GLTransaction", back_populates="job", lazy="dynamic")
    budgets = relationship("JobBudget", back_populates="job", lazy="dynamic")
    billings = relationship("JobBilling", back_populates="job", lazy="dynamic")
    mappings = relationship("JobMapping", back_populates="job", lazy="dynamic")
    exceptions = relationship("Exception", back_populates="job", lazy="dynamic")
    daily_metrics = relationship("JobDailyMetric", back_populates="job", lazy="dynamic")
