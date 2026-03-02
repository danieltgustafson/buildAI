"""Ingestion endpoints for ADP, QBO, and budget data."""

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.auth import TokenData, require_role
from app.database import get_db
from app.schemas.ingest import IngestResult
from app.services.ingest_adp import ingest_adp_csv
from app.services.ingest_budgets import ingest_budgets_csv
from app.services.ingest_qbo import ingest_qbo_csv

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/adp", response_model=IngestResult)
async def upload_adp(
    file: UploadFile,
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin", "ops")),
):
    """Upload an ADP payroll/time export CSV."""
    content = await file.read()
    return ingest_adp_csv(db, content, file.filename or "adp_upload.csv")


@router.post("/qbo", response_model=IngestResult)
async def upload_qbo(
    file: UploadFile,
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin", "ops")),
):
    """Upload a QuickBooks Online transaction export CSV."""
    content = await file.read()
    return ingest_qbo_csv(db, content, file.filename or "qbo_upload.csv")


@router.post("/budgets", response_model=IngestResult)
async def upload_budgets(
    file: UploadFile,
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin", "ops")),
):
    """Upload a budget/estimate CSV."""
    content = await file.read()
    return ingest_budgets_csv(db, content, file.filename or "budgets_upload.csv")
