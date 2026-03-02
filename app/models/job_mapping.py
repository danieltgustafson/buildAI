from typing import Optional


import uuid

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
class JobMapping(Base):
    __tablename__ = "job_mappings"

    mapping_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_system: Mapped[str] = mapped_column(String(20), nullable=False)  # adp/qbo/manual
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=True
    )
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=1.0)
    created_by: Mapped[str] = mapped_column(String(50), nullable=False, default="system")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    job = relationship("Job", back_populates="mappings")
