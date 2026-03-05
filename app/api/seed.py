"""Demo data seeding endpoint (POC only -- disable in production)."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth import TokenData, require_role
from app.database import Base, SessionLocal, get_db

router = APIRouter(prefix="/seed", tags=["demo"])

_seed_lock = threading.Lock()
_seed_state: dict[str, Any] = {
    "running": False,
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "reset": None,
    "profile": None,
    "counts": None,
    "error": None,
}


def _utc_now_iso() -> str:
    return datetime.now(datetime.UTC).isoformat()


def _normalize_profile(profile: str) -> str:
    normalized = profile.strip().lower()
    if normalized not in {"lite", "full"}:
        raise HTTPException(status_code=400, detail="profile must be 'lite' or 'full'")
    return normalized


def _run_seed_job(reset: bool, profile: str) -> None:
    """Execute seeding in a background thread so request timeouts do not kill it."""
    from scripts.seed_demo_data import seed

    db = SessionLocal()
    try:
        counts = seed(db, reset=reset, profile=profile)
        with _seed_lock:
            _seed_state.update(
                {
                    "running": False,
                    "status": "completed",
                    "finished_at": _utc_now_iso(),
                    "counts": counts,
                    "error": None,
                    "profile": profile,
                }
            )
    except Exception as exc:  # noqa: BLE001 - must surface failure details for operators
        db.rollback()
        with _seed_lock:
            _seed_state.update(
                {
                    "running": False,
                    "status": "failed",
                    "finished_at": _utc_now_iso(),
                    "error": str(exc),
                    "profile": profile,
                }
            )
    finally:
        db.close()


@router.get("/demo/status")
def seed_demo_status(
    _user: TokenData = Depends(require_role("admin")),
):
    """Return current seed job status for UI polling/operations checks."""
    with _seed_lock:
        return dict(_seed_state)


@router.post("/demo")
def seed_demo_data(
    reset: bool = False,
    background: bool = True,
    profile: str = "lite",
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin")),
):
    """Populate the database with realistic demo data for presentations.

    Pass ?reset=true to drop and recreate all tables first.
    Default mode runs in background to avoid HTTP timeout/proxy 503 on hosted envs.
    profile=lite uses a smaller dataset footprint for constrained hosts.
    Requires admin role.
    """
    from scripts.seed_demo_data import seed

    normalized_profile = _normalize_profile(profile)

    if background:
        with _seed_lock:
            if _seed_state["running"]:
                return {
                    "status": "running",
                    "message": "Seed already in progress",
                    "started_at": _seed_state["started_at"],
                }

            _seed_state.update(
                {
                    "running": True,
                    "status": "running",
                    "started_at": _utc_now_iso(),
                    "finished_at": None,
                    "reset": reset,
                    "profile": normalized_profile,
                    "counts": None,
                    "error": None,
                }
            )

        worker = threading.Thread(
            target=_run_seed_job,
            args=(reset, normalized_profile),
            daemon=True,
        )
        worker.start()
        return {
            "status": "accepted",
            "message": "Seed job started in background",
            "reset": reset,
            "profile": normalized_profile,
        }

    try:
        counts = seed(db, reset=reset, profile=normalized_profile)
        return {
            "status": "ok",
            "message": "Demo data seeded successfully",
            "counts": counts,
        }
    except Exception as exc:  # noqa: BLE001 - API should return safe error response
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Seed failed: {exc}") from exc


@router.delete("/demo")
def clear_demo_data(
    db: Session = Depends(get_db),
    _user: TokenData = Depends(require_role("admin")),
):
    """Remove all rows from app tables without dropping schema."""
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(delete(table))
        db.commit()
        return {"status": "ok", "message": "Database cleared (all table rows removed)"}
    except Exception as exc:  # noqa: BLE001 - API should return safe error response
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Clear failed: {exc}") from exc
