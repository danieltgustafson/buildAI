"""Shared API dependencies."""

from sqlalchemy.orm import Session

from app.database import get_db

# Re-export for convenience
__all__ = ["get_db", "Session"]
