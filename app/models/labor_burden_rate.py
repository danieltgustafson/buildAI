from typing import Optional


import uuid

from sqlalchemy import Date, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
class LaborBurdenRate(Base):
    __tablename__ = "labor_burden_rates"

    rate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    effective_date: Mapped[str] = mapped_column(Date, nullable=False)
    fica_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.0765)
    futa_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.006)
    suta_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.03)
    workers_comp_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.05)
    benefits_per_hour: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    overhead_multiplier: Mapped[Optional[float]] = mapped_column(Numeric(6, 4), nullable=True)
