"""Demo data seeding endpoint (POC only -- disable in production)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
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

    counts = seed(db, reset=reset)
    return {"status": "ok", "message": "Demo data seeded successfully", "counts": counts}


@router.delete("/demo")
def clear_demo_data(
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin")),
):
    """Drop and recreate all tables without inserting demo rows."""
    from app.database import Base

    bind = db.get_bind()
    db.close()
    Base.metadata.drop_all(bind=bind)
    Base.metadata.create_all(bind=bind)
    return {"status": "ok", "message": "Database cleared (empty schema recreated)"}
