"""create remediation_executions table

Revision ID: 0004_create_remediation_tables
Revises: 0003_create_ai_tables
Create Date: 2026-10-06 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_create_remediation_tables"
down_revision: Union[str, None] = "0003_create_ai_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "remediation_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("ai_report_id", sa.Uuid(), nullable=False),
        sa.Column("source_dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by", sa.String(length=128), nullable=False, server_default="user"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("transformation_plan", json_type, nullable=False),
        sa.Column("pre_metrics", json_type, nullable=False),
        sa.Column("post_metrics", json_type, nullable=False),
        sa.Column("transformation_provenance", json_type, nullable=False),
        sa.Column("result_dataset_version_id", sa.Uuid(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_report_id"], ["ai_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_dataset_version_id"], ["dataset_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["result_dataset_version_id"], ["dataset_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_remediation_executions_run_id",
        "remediation_executions",
        ["analysis_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_remediation_executions_report_id",
        "remediation_executions",
        ["ai_report_id"],
        unique=False,
    )
    op.create_index(
        "ix_remediation_executions_source_version",
        "remediation_executions",
        ["source_dataset_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_remediation_executions_status",
        "remediation_executions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_remediation_executions_result_dataset_version_id",
        "remediation_executions",
        ["result_dataset_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_remediation_executions_result_dataset_version_id", table_name="remediation_executions")
    op.drop_index("ix_remediation_executions_status", table_name="remediation_executions")
    op.drop_index("ix_remediation_executions_source_version", table_name="remediation_executions")
    op.drop_index("ix_remediation_executions_report_id", table_name="remediation_executions")
    op.drop_index("ix_remediation_executions_run_id", table_name="remediation_executions")
    op.drop_table("remediation_executions")
