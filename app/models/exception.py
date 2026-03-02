from typing import Optional


import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
class ExceptionType(str, enum.Enum):
    UNMAPPED_TIME_ENTRY = "UNMAPPED_TIME_ENTRY"
    UNMAPPED_TRANSACTION = "UNMAPPED_TRANSACTION"
    JOB_OVERRUN_RISK = "JOB_OVERRUN_RISK"
    MARGIN_DRIFT = "MARGIN_DRIFT"
    DATA_INTEGRITY = "DATA_INTEGRITY"
class ExceptionSeverity(str, enum.Enum):
    info = "info"
    warn = "warn"
    critical = "critical"
class Exception(Base):
    __tablename__ = "exceptions"

    exception_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=True
    )
    type: Mapped[ExceptionType] = mapped_column(Enum(ExceptionType), nullable=False)
    severity: Mapped[ExceptionSeverity] = mapped_column(
        Enum(ExceptionSeverity), nullable=False, default=ExceptionSeverity.info
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    job = relationship("Job", back_populates="exceptions")
