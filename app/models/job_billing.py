from typing import Optional


import uuid

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
class JobBilling(Base):
    __tablename__ = "job_billing"

    billing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=False
    )
    invoice_date: Mapped[str] = mapped_column(Date, nullable=False)
    amount_billed: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    amount_collected: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    retainage_held: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    raw_source_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    job = relationship("Job", back_populates="billings")
