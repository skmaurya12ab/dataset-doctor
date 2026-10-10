"""Dataset management API endpoints: upload, listing, details, and preview."""

from pathlib import Path
from typing import List, Optional
import uuid
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserDep, DBSessionDep, IngestionServiceDep, StorageServiceDep
from app.core.exceptions import EntityNotFoundException, MalformedFileException
from app.core.logging import get_logger
from app.core.rate_limit import rate_limiter
from app.models.dataset import Dataset, DatasetVersion
from app.schemas.dataset import (
    DatasetListItem,
    DatasetPreviewResponse,
    DatasetRead,
    DatasetUploadResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.post("/upload", response_model=DatasetUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    db: DBSessionDep,
    storage: StorageServiceDep,
    ingestion: IngestionServiceDep,
    current_user: CurrentUserDep,
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    dataset_id: Optional[uuid.UUID] = Form(None),
    change_summary: Optional[str] = Form(None),
) -> DatasetUploadResponse:
    """Upload a tabular dataset (CSV, XLSX, JSON, Parquet).
    
    Validates file integrity, saves original upload, converts canonically to Parquet,
    extracts schema metadata, persists immutable version records, and associates ownership.
    """
    rate_limiter.enforce(f"upload:{current_user.id}", max_requests=20, window_seconds=60, action_name="Dataset upload")

    if not file or not file.filename:
        raise MalformedFileException("No file provided in upload request.")

    # 1. Determine and validate format
    format_key = ingestion.determine_format(file.filename)

    # 2. Determine target dataset & version number
    parent_version_id = None
    target_dataset: Optional[Dataset] = None

    if dataset_id:
        # Uploading a new version to an existing dataset - verify ownership
        res = await db.execute(
            select(Dataset)
            .options(selectinload(Dataset.versions))
            .where(Dataset.id == dataset_id, Dataset.owner_id == current_user.id)
        )
        target_dataset = res.scalar_one_or_none()
        if not target_dataset:
            raise EntityNotFoundException("Dataset", str(dataset_id))

        existing_versions = sorted(target_dataset.versions, key=lambda v: v.version_number)
        latest_version = existing_versions[-1]
        target_version_number = latest_version.version_number + 1
        parent_version_id = latest_version.id
        resolved_dataset_id = target_dataset.id
        dataset_name = target_dataset.name
    else:
        # New dataset
        resolved_dataset_id = uuid.uuid4()
        target_version_number = 1
        dataset_name = name or Path(file.filename).stem or f"Dataset_{resolved_dataset_id.hex[:6]}"

    # 3. Stream and persist original file to disk with SHA-256 calculation
    saved_file_path, sha256_hash, file_size_bytes = await storage.save_uploaded_stream(
        dataset_id=resolved_dataset_id,
        version_number=target_version_number,
        filename=file.filename,
        file_stream=file.file,
    )

    # 4. Check for duplicate upload in existing dataset
    if target_dataset:
        for v in target_dataset.versions:
            if v.sha256_hash == sha256_hash:
                logger.info(
                    "Identical file upload detected for dataset %s (matches version %d)",
                    resolved_dataset_id,
                    v.version_number,
                )
                return DatasetUploadResponse(
                    dataset_id=resolved_dataset_id,
                    version_id=v.id,
                    version_number=v.version_number,
                    file_name=v.file_name,
                    row_count=v.row_count,
                    column_count=v.column_count,
                    storage_format="parquet",
                    status="ALREADY_EXISTS",
                )

    # 5. Parse dataset into standardized DataFrame container
    loaded_data = ingestion.parse_file(
        file_path=saved_file_path,
        format_key=format_key,
        original_filename=file.filename,
    )

    # 6. Normalize canonical Parquet file
    parquet_path = storage.save_canonical_parquet(
        df=loaded_data.dataframe,
        dataset_id=resolved_dataset_id,
        version_number=target_version_number,
    )

    # 7. Extract deterministic metadata schema
    raw_schema = ingestion.extract_raw_schema(loaded_data.dataframe)
    row_count = len(loaded_data.dataframe)
    column_count = len(loaded_data.dataframe.columns)

    # 8. Create database records
    if not target_dataset:
        target_dataset = Dataset(
            id=resolved_dataset_id,
            name=dataset_name,
            description=description,
            owner_id=current_user.id,
        )
        db.add(target_dataset)
        await db.flush()

    version_record = DatasetVersion(
        id=uuid.uuid4(),
        dataset_id=resolved_dataset_id,
        parent_version_id=parent_version_id,
        version_number=target_version_number,
        change_summary=change_summary or ("Initial upload" if target_version_number == 1 else f"Version {target_version_number}"),
        file_name=storage.sanitize_filename(file.filename),
        storage_path=str(parquet_path.relative_to(storage.base_dir)),
        file_size_bytes=file_size_bytes,
        sha256_hash=sha256_hash,
        row_count=row_count,
        column_count=column_count,
        raw_schema=raw_schema,
    )
    db.add(version_record)
    await db.commit()

    logger.info(
        "Successfully registered dataset %s ('%s') v%d with %d rows and %d cols for user %s",
        resolved_dataset_id,
        dataset_name,
        target_version_number,
        row_count,
        column_count,
        current_user.id,
    )

    return DatasetUploadResponse(
        dataset_id=resolved_dataset_id,
        version_id=version_record.id,
        version_number=target_version_number,
        file_name=version_record.file_name,
        row_count=row_count,
        column_count=column_count,
        storage_format="parquet",
        status="READY",
    )


@router.get("", response_model=List[DatasetListItem])
async def list_datasets(
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> List[DatasetListItem]:
    """Retrieve summary listing of all datasets and their latest version information for current user."""
    stmt = (
        select(Dataset)
        .options(selectinload(Dataset.versions))
        .where(Dataset.owner_id == current_user.id)
        .order_by(desc(Dataset.updated_at))
    )
    result = await db.execute(stmt)
    datasets = result.scalars().all()

    items: List[DatasetListItem] = []
    for d in datasets:
        if not d.versions:
            continue
        # Get latest version
        latest_version = sorted(d.versions, key=lambda v: v.version_number)[-1]
        items.append(
            DatasetListItem(
                dataset_id=d.id,
                name=d.name,
                description=d.description,
                latest_version_number=latest_version.version_number,
                latest_row_count=latest_version.row_count,
                latest_column_count=latest_version.column_count,
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
        )
    return items


@router.get("/{dataset_id}", response_model=DatasetRead)
async def get_dataset_detail(
    dataset_id: uuid.UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> DatasetRead:
    """Retrieve detailed dataset information including all historical versions."""
    stmt = (
        select(Dataset)
        .options(selectinload(Dataset.versions))
        .where(Dataset.id == dataset_id, Dataset.owner_id == current_user.id)
    )
    result = await db.execute(stmt)
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise EntityNotFoundException("Dataset", str(dataset_id))

    return DatasetRead.model_validate(dataset)


@router.get("/{dataset_id}/versions/{version_num}/preview", response_model=DatasetPreviewResponse)
async def get_dataset_version_preview(
    dataset_id: uuid.UUID,
    version_num: int,
    db: DBSessionDep,
    storage: StorageServiceDep,
    current_user: CurrentUserDep,
    limit: int = Query(default=20, ge=1, le=100, description="Maximum rows to preview (1-100)"),
    offset: int = Query(default=0, ge=0, description="Offset row index"),
) -> DatasetPreviewResponse:
    """Retrieve a strictly bounded row-level preview of a dataset version."""
    stmt = (
        select(DatasetVersion)
        .join(Dataset, DatasetVersion.dataset_id == Dataset.id)
        .where(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.version_number == version_num,
            Dataset.owner_id == current_user.id,
        )
    )
    result = await db.execute(stmt)
    version = result.scalar_one_or_none()
    if not version:
        raise EntityNotFoundException("DatasetVersion", f"{dataset_id}/v{version_num}")

    preview_df, total_rows, total_cols = storage.read_preview(
        dataset_id=dataset_id,
        version_number=version_num,
        limit=limit,
        offset=offset,
    )

    # Convert preview rows to JSON-safe dictionary records
    rows = preview_df.to_dict(orient="records")
    dtypes = {str(col): str(preview_df[col].dtype) for col in preview_df.columns}

    return DatasetPreviewResponse(
        dataset_id=dataset_id,
        version_number=version_num,
        total_rows=total_rows,
        total_columns=total_cols,
        file_size_bytes=version.file_size_bytes,
        columns=list(preview_df.columns),
        dtypes=dtypes,
        rows=rows,
        limit=limit,
        offset=offset,
    )
