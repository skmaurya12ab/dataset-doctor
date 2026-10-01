"""create analysis_runs and quality_issues tables

Revision ID: 0002_create_analysis_tables
Revises: 0001_initial
Create Date: 2026-10-01 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_create_analysis_tables"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    # 1. Create analysis_runs table
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("target_column", sa.String(length=128), nullable=True),
        sa.Column("problem_type", sa.String(length=32), nullable=True),
        sa.Column("engine_version", sa.String(length=32), nullable=False),
        sa.Column("analyzer_versions", json_type, nullable=False),
        sa.Column("ml_readiness_score", sa.Float(), nullable=True),
        sa.Column("heuristic_breakdown", json_type, nullable=True),
        sa.Column("total_issues_count", sa.Integer(), nullable=False),
        sa.Column("critical_issues_count", sa.Integer(), nullable=False),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("summary_metrics", json_type, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analysis_runs_dataset_version_id"), "analysis_runs", ["dataset_version_id"], unique=False)
    op.create_index(op.f("ix_analysis_runs_status"), "analysis_runs", ["status"], unique=False)

    # 2. Create quality_issues table
    op.create_table(
        "quality_issues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("analyzer_version", sa.String(length=32), nullable=False),
        sa.Column("parameters_used", json_type, nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("column_name", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", json_type, nullable=False),
        sa.Column("remediation_hint", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quality_issues_analysis_run_id"), "quality_issues", ["analysis_run_id"], unique=False)
    op.create_index(op.f("ix_quality_issues_dataset_version_id"), "quality_issues", ["dataset_version_id"], unique=False)
    op.create_index(op.f("ix_quality_issues_module"), "quality_issues", ["module"], unique=False)
    op.create_index(op.f("ix_quality_issues_category"), "quality_issues", ["category"], unique=False)
    op.create_index(op.f("ix_quality_issues_severity"), "quality_issues", ["severity"], unique=False)
    op.create_index(op.f("ix_quality_issues_column_name"), "quality_issues", ["column_name"], unique=False)
    op.create_index("ix_quality_issues_run_severity", "quality_issues", ["analysis_run_id", "severity"], unique=False)
    op.create_index("ix_quality_issues_run_module", "quality_issues", ["analysis_run_id", "module"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_quality_issues_run_module", table_name="quality_issues")
    op.drop_index("ix_quality_issues_run_severity", table_name="quality_issues")
    op.drop_index(op.f("ix_quality_issues_column_name"), table_name="quality_issues")
    op.drop_index(op.f("ix_quality_issues_severity"), table_name="quality_issues")
    op.drop_index(op.f("ix_quality_issues_category"), table_name="quality_issues")
    op.drop_index(op.f("ix_quality_issues_module"), table_name="quality_issues")
    op.drop_index(op.f("ix_quality_issues_dataset_version_id"), table_name="quality_issues")
    op.drop_index(op.f("ix_quality_issues_analysis_run_id"), table_name="quality_issues")
    op.drop_table("quality_issues")
    op.drop_index(op.f("ix_analysis_runs_status"), table_name="analysis_runs")
    op.drop_index(op.f("ix_analysis_runs_dataset_version_id"), table_name="analysis_runs")
    op.drop_table("analysis_runs")
