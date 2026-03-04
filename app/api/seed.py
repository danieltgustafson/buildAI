"""Demo data seeding endpoint (POC only -- disable in production)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth import TokenData, require_role
from app.database import get_db

router = APIRouter(prefix="/seed", tags=["demo"])


@router.post("/demo")
def seed_demo_data(
    reset: bool = False,
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin")),
):
    """Populate the database with realistic demo data for presentations.

    Pass ?reset=true to drop and recreate all tables first.
    Requires admin role.
    """
    from scripts.seed_demo_data import seed

    try:
        counts = seed(db, reset=reset)
        return {"status": "ok", "message": "Demo data seeded successfully", "counts": counts}
    except Exception as exc:  # noqa: BLE001 - API should return safe error response
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Seed failed: {exc}") from exc


@router.delete("/demo")
def clear_demo_data(
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin")),
):
    """Remove all rows from app tables without dropping schema."""
    from app.database import Base

    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(delete(table))
        db.commit()
        return {"status": "ok", "message": "Database cleared (all table rows removed)"}
    except Exception as exc:  # noqa: BLE001 - API should return safe error response
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Clear failed: {exc}") from exc
