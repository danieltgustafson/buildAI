from typing import Optional


import uuid

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
class TimeEntry(Base):
    __tablename__ = "time_entries"

    time_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=True
    )
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=True
    )
    work_date: Mapped[str] = mapped_column(Date, nullable=False)
    hours: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    pay_rate: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    raw_source_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cost_code_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cost_codes.cost_code_id"), nullable=True
    )
    labor_cost_direct: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    labor_cost_burdened: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    job = relationship("Job", back_populates="time_entries")
    employee = relationship("Employee", back_populates="time_entries")
