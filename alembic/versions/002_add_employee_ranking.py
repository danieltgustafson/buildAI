"""Add ranking_score and ranking_title columns to employees.

Revision ID: 002
Revises: 001
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("ranking_score", sa.Integer, nullable=True))
    op.add_column("employees", sa.Column("ranking_title", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "ranking_title")
    op.drop_column("employees", "ranking_score")
