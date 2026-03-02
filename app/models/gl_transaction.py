from typing import Optional


import enum
import uuid

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
class TransactionCategory(str, enum.Enum):
    materials = "materials"
    sub = "sub"
    equipment = "equipment"
    permit = "permit"
    other = "other"
class GLTransaction(Base):
    __tablename__ = "gl_transactions"

    txn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=True
    )
    txn_date: Mapped[str] = mapped_column(Date, nullable=False)
    vendor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[TransactionCategory] = mapped_column(
        Enum(TransactionCategory), nullable=False, default=TransactionCategory.other
    )
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    raw_source_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cost_code_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cost_codes.cost_code_id"), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    job = relationship("Job", back_populates="gl_transactions")
