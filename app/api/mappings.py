"""Job mapping endpoints for resolving ADP/QBO source keys to internal jobs."""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import TokenData, get_current_user, require_role
from app.database import get_db
from app.models.gl_transaction import GLTransaction
from app.models.job_mapping import JobMapping
from app.models.time_entry import TimeEntry
from app.schemas.mapping import MappingCreate, MappingRead, UnresolvedMapping

router = APIRouter(prefix="/mappings", tags=["mappings"])


@router.post("", response_model=MappingRead, status_code=201)
def create_mapping(
    payload: MappingCreate,
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin", "ops")),
):
    """Create a new source key -> job mapping."""
    mapping = JobMapping(**payload.model_dump())
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping


@router.get("", response_model=list[MappingRead])
def list_mappings(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """List all job mappings."""
    return db.query(JobMapping).all()


@router.get("/unresolved", response_model=list[UnresolvedMapping])
def list_unresolved(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Show source keys from ingested data that have no mapping to a job.

    Combines unmapped time entries (ADP) and unmapped transactions (QBO).
    """
    results: list[UnresolvedMapping] = []

    # Find ADP source keys in time_entries with no job_id
    unmapped_time = (
        db.query(
            TimeEntry.raw_source_id,
            func.count().label("cnt"),
        )
        .filter(TimeEntry.job_id.is_(None), TimeEntry.raw_source_id.isnot(None))
        .group_by(TimeEntry.raw_source_id)
        .all()
    )

    # Deduplicate by extracting the ADP job ref pattern
    adp_keys: dict[str, int] = {}
    for row in unmapped_time:
        # raw_source_id format: "adp:<hash>:<idx>"
        parts = row.raw_source_id.split(":") if row.raw_source_id else []
        key = parts[0] if parts else "unknown"
        adp_keys[key] = adp_keys.get(key, 0) + row.cnt

    for key, count in adp_keys.items():
        results.append(UnresolvedMapping(source_system="adp", source_key=key, occurrence_count=count))

    # Find QBO source keys in gl_transactions with no job_id
    unmapped_txns = (
        db.query(
            GLTransaction.raw_source_id,
            func.count().label("cnt"),
        )
        .filter(GLTransaction.job_id.is_(None), GLTransaction.raw_source_id.isnot(None))
        .group_by(GLTransaction.raw_source_id)
        .all()
    )

    qbo_keys: dict[str, int] = {}
    for row in unmapped_txns:
        parts = row.raw_source_id.split(":") if row.raw_source_id else []
        key = parts[0] if parts else "unknown"
        qbo_keys[key] = qbo_keys.get(key, 0) + row.cnt

    for key, count in qbo_keys.items():
        results.append(UnresolvedMapping(source_system="qbo", source_key=key, occurrence_count=count))

    return results
