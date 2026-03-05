"""Production startup runner.

Waits for DB readiness, applies Alembic migrations, then starts the API.
"""

from __future__ import annotations

import os
import time

import uvicorn
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.config import settings


def wait_for_database(max_attempts: int = 30, delay_seconds: int = 2) -> None:
    """Block until a DB connection succeeds or raise on timeout."""
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            engine = create_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as exc:  # noqa: BLE001 - startup should retry any DB failure
            last_error = exc
            print(f"[startup] database not ready (attempt {attempt}/{max_attempts}): {exc}")
            time.sleep(delay_seconds)

    raise RuntimeError("Database did not become ready in time") from last_error


def run_migrations() -> None:
    """Apply all Alembic migrations to head."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)
    command.upgrade(alembic_cfg, "head")


def main() -> None:
    wait_for_database()
    run_migrations()

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
