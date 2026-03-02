"""Exception/flag endpoints."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.exception import Exception as ExceptionModel
from app.schemas.exception import ExceptionRead

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


@router.get("", response_model=list[ExceptionRead])
def list_exceptions(
    open_only: bool = Query(True, description="Only show unresolved exceptions"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """List data quality exceptions and job flags."""
    q = db.query(ExceptionModel)
    if open_only:
        q = q.filter(ExceptionModel.resolved_at.is_(None))
    return q.order_by(ExceptionModel.created_at.desc()).all()


@router.post("/{exception_id}/resolve", response_model=ExceptionRead)
def resolve_exception(
    exception_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Mark an exception as resolved."""
    exc = db.query(ExceptionModel).filter(ExceptionModel.exception_id == exception_id).one()
    exc.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(exc)
    return exc
