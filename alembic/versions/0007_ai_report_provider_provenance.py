"""Persist AI report provider provenance.

Revision ID: 0007_report_provider_provenance
Revises: 0006_email_delivery_limits
Create Date: 2026-10-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_report_provider_provenance"
down_revision: Union[str, None] = "0006_email_delivery_limits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_reports",
        sa.Column("provider", sa.String(length=64), server_default="unknown", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("ai_reports", "provider")
