"""Add scheduling tables: crew_type on employees, job_labor_demand, schedule_assignments.

Revision ID: 001
Revises:
Create Date: 2026-04-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("crew_type", sa.String(100), nullable=True),
    )

    op.create_table(
        "job_labor_demand",
        sa.Column("demand_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.job_id"), nullable=False),
        sa.Column("year_month", sa.String(7), nullable=False),
        sa.Column("crew_type", sa.String(100), nullable=True),
        sa.Column("man_days_needed", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.UniqueConstraint("job_id", "year_month", "crew_type", name="uq_job_labor_demand"),
    )

    op.create_table(
        "schedule_assignments",
        sa.Column("assignment_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "employee_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.employee_id"),
            nullable=False,
        ),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.job_id"), nullable=True),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.UniqueConstraint("employee_id", "work_date", name="uq_schedule_assignment"),
    )

    op.create_index("ix_schedule_assignments_work_date", "schedule_assignments", ["work_date"])
    op.create_index("ix_job_labor_demand_year_month", "job_labor_demand", ["year_month"])


def downgrade() -> None:
    op.drop_index("ix_job_labor_demand_year_month", table_name="job_labor_demand")
    op.drop_index("ix_schedule_assignments_work_date", table_name="schedule_assignments")
    op.drop_table("schedule_assignments")
    op.drop_table("job_labor_demand")
    op.drop_column("employees", "crew_type")
