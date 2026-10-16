"""add persistent email delivery abuse limits

Revision ID: 0006_email_delivery_limits
Revises: 0005_create_auth_and_user_tables
Create Date: 2026-10-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_email_delivery_limits"
down_revision: Union[str, None] = "0005_create_auth_and_user_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_delivery_counters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bucket_date", sa.Date(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    quota_table = sa.table(
        "email_delivery_counters",
        sa.column("id", sa.Integer()),
        sa.column("bucket_date", sa.Date()),
        sa.column("attempt_count", sa.Integer()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.get_bind().execute(
        sa.insert(quota_table).values(
            id=1,
            bucket_date=sa.func.current_date(),
            attempt_count=0,
            updated_at=sa.func.current_timestamp(),
        )
    )
    op.create_table(
        "email_delivery_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_delivery_attempts_user_id", "email_delivery_attempts", ["user_id"])
    op.create_index("ix_email_delivery_attempts_created_at", "email_delivery_attempts", ["created_at"])
    op.create_index(
        "ix_email_delivery_attempt_user_created",
        "email_delivery_attempts",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_delivery_attempt_user_created", table_name="email_delivery_attempts")
    op.drop_index("ix_email_delivery_attempts_created_at", table_name="email_delivery_attempts")
    op.drop_index("ix_email_delivery_attempts_user_id", table_name="email_delivery_attempts")
    op.drop_table("email_delivery_attempts")
    op.drop_table("email_delivery_counters")
