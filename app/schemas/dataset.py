"""Pydantic schemas for dataset ingestion, listing, inspection, and preview."""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class ColumnSchemaItem(BaseModel):
    """Metadata for an individual dataset column."""

    name: str = Field(description="Column header name")
    dtype: str = Field(description="Inferred or storage data type")


class RawSchema(BaseModel):
    """Container for tabular schema definitions."""

    columns: List[ColumnSchemaItem] = Field(default_factory=list)


class DatasetVersionRead(BaseModel):
    """Schema representing an immutable version snapshot."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    parent_version_id: Optional[uuid.UUID] = None
    version_number: int
    change_summary: Optional[str] = None
    file_name: str
    file_size_bytes: int
    sha256_hash: str
    row_count: int
    column_count: int
    raw_schema: Dict[str, Any]
    created_at: datetime


class DatasetRead(BaseModel):
    """Schema for complete dataset details including all versions."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    versions: List[DatasetVersionRead] = Field(default_factory=list)


class DatasetListItem(BaseModel):
    """Lightweight summary schema for dataset collection listings."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: uuid.UUID
    name: str
    description: Optional[str] = None
    latest_version_number: int
    latest_row_count: int
    latest_column_count: int
    created_at: datetime
    updated_at: datetime


class DatasetUploadResponse(BaseModel):
    """Response returned upon successful file upload and Parquet normalization."""

    dataset_id: uuid.UUID
    version_id: uuid.UUID
    version_number: int
    file_name: str
    row_count: int
    column_count: int
    storage_format: str = "parquet"
    status: str = "READY"


class DatasetPreviewResponse(BaseModel):
    """Strictly constrained row-level data preview for frontend inspection."""

    dataset_id: uuid.UUID
    version_number: int
    total_rows: int
    total_columns: int
    file_size_bytes: int
    columns: List[str]
    dtypes: Dict[str, str]
    rows: List[Dict[str, Any]]
    limit: int
    offset: int
