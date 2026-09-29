"""Tests for DatasetIngestionService and format-specific loaders."""

from pathlib import Path
import pytest
from app.core.exceptions import MalformedFileException, UnsupportedFileFormatException
from app.services.ingestion import DatasetIngestionService


def test_supported_format_determination() -> None:
    """Verify format detection and rejection of unsupported extensions."""
    ingestion = DatasetIngestionService()

    assert ingestion.determine_format("data.csv") == "csv"
    assert ingestion.determine_format("DATA.CSV") == "csv"
    assert ingestion.determine_format("sheet.xlsx") == "xlsx"
    assert ingestion.determine_format("records.json") == "json"
    assert ingestion.determine_format("dataset.parquet") == "parquet"

    with pytest.raises(UnsupportedFileFormatException):
        ingestion.determine_format("document.pdf")

    with pytest.raises(UnsupportedFileFormatException):
        ingestion.determine_format("executable.exe")


def test_load_valid_csv(fixtures_dir: Path) -> None:
    """Verify loading standard CSV."""
    ingestion = DatasetIngestionService()
    file_path = fixtures_dir / "simple.csv"

    loaded = ingestion.parse_file(file_path, "csv", "simple.csv")
    assert loaded.original_format == "csv"
    assert len(loaded.dataframe) == 5
    assert len(loaded.dataframe.columns) == 3
    assert list(loaded.dataframe.columns) == ["id", "name", "score"]

    schema = ingestion.extract_raw_schema(loaded.dataframe)
    assert len(schema["columns"]) == 3
    assert schema["columns"][0]["name"] == "id"


def test_load_valid_xlsx(fixtures_dir: Path) -> None:
    """Verify loading Excel workbook."""
    ingestion = DatasetIngestionService()
    file_path = fixtures_dir / "sample.xlsx"

    loaded = ingestion.parse_file(file_path, "xlsx", "sample.xlsx")
    assert loaded.original_format == "xlsx"
    assert len(loaded.dataframe) == 5
    assert len(loaded.dataframe.columns) == 3


def test_load_valid_json(fixtures_dir: Path) -> None:
    """Verify loading JSON records."""
    ingestion = DatasetIngestionService()
    file_path = fixtures_dir / "sample.json"

    loaded = ingestion.parse_file(file_path, "json", "sample.json")
    assert loaded.original_format == "json"
    assert len(loaded.dataframe) == 5
    assert len(loaded.dataframe.columns) == 3


def test_load_valid_parquet(fixtures_dir: Path) -> None:
    """Verify loading Parquet file."""
    ingestion = DatasetIngestionService()
    file_path = fixtures_dir / "sample.parquet"

    loaded = ingestion.parse_file(file_path, "parquet", "sample.parquet")
    assert loaded.original_format == "parquet"
    assert len(loaded.dataframe) == 5
    assert len(loaded.dataframe.columns) == 3


def test_reject_empty_csv(fixtures_dir: Path) -> None:
    """Verify that an empty file raises MalformedFileException."""
    ingestion = DatasetIngestionService()
    empty_file = fixtures_dir / "empty.csv"

    with pytest.raises(MalformedFileException, match="empty|no headers"):
        ingestion.parse_file(empty_file, "csv", "empty.csv")


def test_reject_invalid_excel_signature(tmp_path: Path) -> None:
    """Verify rejection of a non-ZIP file with .xlsx extension."""
    ingestion = DatasetIngestionService()
    fake_excel = tmp_path / "fake.xlsx"
    fake_excel.write_text("not an excel file")

    with pytest.raises(MalformedFileException, match="signature|XLSX"):
        ingestion.parse_file(fake_excel, "xlsx", "fake.xlsx")


def test_reject_invalid_parquet_signature(tmp_path: Path) -> None:
    """Verify rejection of a non-parquet file with .parquet extension."""
    ingestion = DatasetIngestionService()
    fake_parquet = tmp_path / "fake.parquet"
    fake_parquet.write_bytes(b"NOT_A_PARQUET_HEADER")

    with pytest.raises(MalformedFileException, match="magic header|signature"):
        ingestion.parse_file(fake_parquet, "parquet", "fake.parquet")
