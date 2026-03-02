from pydantic import BaseModel


class IngestResult(BaseModel):
    source: str
    rows_ingested: int
    rows_mapped: int
    rows_unmapped: int
    exceptions_created: int
    message: str
