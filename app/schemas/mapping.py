from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class MappingCreate(BaseModel):
    source_system: str  # adp / qbo / manual
    source_key: str
    job_id: UUID | None = None
    confidence: float = 1.0
    created_by: str = "user"
    notes: str | None = None


class MappingRead(BaseModel):
    mapping_id: UUID
    source_system: str
    source_key: str
    job_id: UUID | None = None
    confidence: float
    created_by: str
    notes: str | None = None

    model_config = {"from_attributes": True}


class UnresolvedMapping(BaseModel):
    source_system: str
    source_key: str
    occurrence_count: int
