"""create ai_reports and finding_explanations tables

Revision ID: 0003_create_ai_tables
Revises: 0002_create_analysis_tables
Create Date: 2026-10-06 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_create_ai_tables"
down_revision: Union[str, None] = "0002_create_analysis_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    # 1. Create ai_reports table
    op.create_table(
        "ai_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("provider_model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("risk_assessment", json_type, nullable=False),
        sa.Column("remediation_plan", json_type, nullable=False),
        sa.Column("transformation_specs", json_type, nullable=False),
        sa.Column("ml_preparation_plan", json_type, nullable=False),
        sa.Column("generated_python_code", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_reports_analysis_run_id"), "ai_reports", ["analysis_run_id"], unique=False)
    op.create_index(op.f("ix_ai_reports_provider_model"), "ai_reports", ["provider_model"], unique=False)
    op.create_index(
        "ix_ai_reports_run_model_version",
        "ai_reports",
        ["analysis_run_id", "provider_model", "prompt_version"],
        unique=False,
    )

    # 2. Create finding_explanations table
    op.create_table(
        "finding_explanations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quality_issue_id", sa.Uuid(), nullable=False),
        sa.Column("provider_model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("explanation_text", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("practical_impact", sa.Text(), nullable=False),
        sa.Column("recommended_actions", json_type, nullable=False),
        sa.Column("limitations", json_type, nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["quality_issue_id"], ["quality_issues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_finding_explanations_quality_issue_id"), "finding_explanations", ["quality_issue_id"], unique=False)
    op.create_index(op.f("ix_finding_explanations_provider_model"), "finding_explanations", ["provider_model"], unique=False)
    op.create_index(
        "ix_finding_explanations_issue_model_version",
        "finding_explanations",
        ["quality_issue_id", "provider_model", "prompt_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_finding_explanations_issue_model_version", table_name="finding_explanations")
    op.drop_index(op.f("ix_finding_explanations_provider_model"), table_name="finding_explanations")
    op.drop_index(op.f("ix_finding_explanations_quality_issue_id"), table_name="finding_explanations")
    op.drop_table("finding_explanations")

    op.drop_index("ix_ai_reports_run_model_version", table_name="ai_reports")
    op.drop_index(op.f("ix_ai_reports_provider_model"), table_name="ai_reports")
    op.drop_index(op.f("ix_ai_reports_analysis_run_id"), table_name="ai_reports")
    op.drop_table("ai_reports")
