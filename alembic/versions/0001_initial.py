"""create datasets and dataset_versions tables

Revision ID: 0001_initial
Revises: 
Create Date: 2026-09-29 17:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create datasets table
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_datasets_name"), "datasets", ["name"], unique=False)

    # 2. Create dataset_versions table
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("parent_version_id", sa.Uuid(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("change_summary", sa.String(length=255), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("raw_schema", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["dataset_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "version_number", name="uq_dataset_version_number"),
    )
    op.create_index(op.f("ix_dataset_versions_dataset_id"), "dataset_versions", ["dataset_id"], unique=False)
    op.create_index(op.f("ix_dataset_versions_parent_version_id"), "dataset_versions", ["parent_version_id"], unique=False)
    op.create_index(op.f("ix_dataset_versions_sha256_hash"), "dataset_versions", ["sha256_hash"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_dataset_versions_sha256_hash"), table_name="dataset_versions")
    op.drop_index(op.f("ix_dataset_versions_parent_version_id"), table_name="dataset_versions")
    op.drop_index(op.f("ix_dataset_versions_dataset_id"), table_name="dataset_versions")
    op.drop_table("dataset_versions")
    op.drop_index(op.f("ix_datasets_name"), table_name="datasets")
    op.drop_table("datasets")
