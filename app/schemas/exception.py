from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.exception import ExceptionSeverity, ExceptionType


class ExceptionRead(BaseModel):
    exception_id: UUID
    job_id: UUID | None = None
    type: ExceptionType
    severity: ExceptionSeverity
    message: str
    source_ref: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None

    model_config = {"from_attributes": True}
