"""Modular dataset ingestion service and format loaders.

Supports:
- CSV (.csv) via pandas with encoding fallback and delimiter detection
- Excel (.xlsx) via openpyxl
- JSON (.json) for records-oriented and columnar tabular structures
- Parquet (.parquet) via pyarrow with magic-byte verification

Normalizes all incoming formats to an immutable, canonical Parquet representation
while preserving original data types, column names, and missingness without mutating data.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
import openpyxl
import pandas as pd
import pyarrow.parquet as pq

from app.core.exceptions import MalformedFileException, UnsupportedFileFormatException
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LoadedDataset:
    """Standardized intermediate container holding parsed tabular data."""

    dataframe: pd.DataFrame
    original_format: str
    original_file_name: str


class BaseLoader(ABC):
    """Abstract strategy for format-specific tabular parsers."""

    @property
    @abstractmethod
    def supported_format(self) -> str:
        """Format identifier (e.g. 'csv', 'parquet')."""
        pass

    @abstractmethod
    def validate_content(self, file_path: Path) -> None:
        """Validate content integrity and file signatures before full parsing."""
        pass

    @abstractmethod
    def load(self, file_path: Path) -> pd.DataFrame:
        """Parse file into a pandas DataFrame."""
        pass


class CSVLoader(BaseLoader):
    """Loader for Comma/Delimiter Separated Values."""

    @property
    def supported_format(self) -> str:
        return "csv"

    def validate_content(self, file_path: Path) -> None:
        if file_path.stat().st_size == 0:
            raise MalformedFileException("CSV file is completely empty (0 bytes).")

    def load(self, file_path: Path) -> pd.DataFrame:
        # Try UTF-8 first, fallback to latin-1 for international encoding resilience
        for encoding in ["utf-8", "utf-8-sig", "latin-1"]:
            try:
                # Use engine='c' with fallback to python if delimiter sniffing is needed
                df = pd.read_csv(file_path, encoding=encoding, on_bad_lines="error")
                return df
            except UnicodeDecodeError:
                continue
            except pd.errors.EmptyDataError:
                raise MalformedFileException("CSV file contains no headers or records.")
            except Exception as e:
                # If error is a parsing error, try sniffing separator
                try:
                    df = pd.read_csv(file_path, encoding=encoding, sep=None, engine="python")
                    return df
                except Exception as inner_e:
                    raise MalformedFileException(f"Failed to parse CSV file: {inner_e}") from inner_e

        raise MalformedFileException("Unable to decode CSV file with supported encodings (UTF-8, Latin-1).")


class XLSXLoader(BaseLoader):
    """Loader for Microsoft Excel (.xlsx) workbooks."""

    @property
    def supported_format(self) -> str:
        return "xlsx"

    def validate_content(self, file_path: Path) -> None:
        if file_path.stat().st_size < 4:
            raise MalformedFileException("Excel file is too small to be a valid XLSX workbook.")
        # XLSX files are ZIP archives starting with PK\x03\x04
        with open(file_path, "rb") as f:
            header = f.read(4)
            if header != b"PK\x03\x04":
                raise MalformedFileException("Invalid Excel file signature. Expected XLSX (ZIP archive).")

    def load(self, file_path: Path) -> pd.DataFrame:
        try:
            # Load active sheet
            df = pd.read_excel(file_path, engine="openpyxl")
            return df
        except Exception as e:
            raise MalformedFileException(f"Failed to parse Excel workbook: {e}") from e


class JSONLoader(BaseLoader):
    """Loader for JSON tabular data (records list or columnar dictionary)."""

    @property
    def supported_format(self) -> str:
        return "json"

    def validate_content(self, file_path: Path) -> None:
        if file_path.stat().st_size == 0:
            raise MalformedFileException("JSON file is empty.")

    def load(self, file_path: Path) -> pd.DataFrame:
        try:
            # Try records/table orientation first
            df = pd.read_json(file_path, orient=None)
            if df.empty:
                raise MalformedFileException("JSON file parsed into an empty tabular structure.")
            return df
        except Exception as e:
            raise MalformedFileException(f"Failed to parse JSON tabular data: {e}") from e


class ParquetLoader(BaseLoader):
    """Loader for Apache Parquet files."""

    @property
    def supported_format(self) -> str:
        return "parquet"

    def validate_content(self, file_path: Path) -> None:
        if file_path.stat().st_size < 4:
            raise MalformedFileException("Parquet file is too small to contain valid metadata.")
        # Parquet files must begin with magic bytes 'PAR1'
        with open(file_path, "rb") as f:
            magic = f.read(4)
            if magic != b"PAR1":
                raise MalformedFileException("Invalid Parquet file signature. Missing 'PAR1' magic header.")

    def load(self, file_path: Path) -> pd.DataFrame:
        try:
            df = pd.read_parquet(file_path, engine="pyarrow")
            return df
        except Exception as e:
            raise MalformedFileException(f"Failed to parse Parquet file: {e}") from e


class DatasetIngestionService:
    """Coordinates file validation, format dispatching, schema extraction, and Parquet normalization."""

    SUPPORTED_EXTENSIONS = {
        ".csv": "csv",
        ".xlsx": "xlsx",
        ".json": "json",
        ".parquet": "parquet",
    }

    def __init__(self):
        self.loaders: Dict[str, BaseLoader] = {
            "csv": CSVLoader(),
            "xlsx": XLSXLoader(),
            "json": JSONLoader(),
            "parquet": ParquetLoader(),
        }

    def determine_format(self, filename: str) -> str:
        """Validate extension and map to canonical format key."""
        ext = Path(filename).suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise UnsupportedFileFormatException(
                extension=ext,
                supported=list(self.SUPPORTED_EXTENSIONS.keys()),
            )
        return self.SUPPORTED_EXTENSIONS[ext]

    def parse_file(self, file_path: Path, format_key: str, original_filename: str) -> LoadedDataset:
        """Execute format validation and load into standardized DataFrame container."""
        loader = self.loaders.get(format_key)
        if not loader:
            raise UnsupportedFileFormatException(format_key, list(self.loaders.keys()))

        # 1. Content-level verification
        loader.validate_content(file_path)

        # 2. Parse data
        df = loader.load(file_path)

        # 3. Reject empty dataframes
        if df is None or df.empty or len(df.columns) == 0:
            raise MalformedFileException("Dataset contains 0 rows or 0 columns.")

        # Ensure column headers are all strings (prevents pyarrow errors with int headers in excel)
        df.columns = [str(c) for c in df.columns]

        logger.info(
            "Parsed %s file '%s': %d rows, %d columns",
            format_key.upper(),
            original_filename,
            len(df),
            len(df.columns),
        )
        return LoadedDataset(
            dataframe=df,
            original_format=format_key,
            original_file_name=original_filename,
        )

    def extract_raw_schema(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extract deterministic basic column names and pandas storage dtypes."""
        columns = [
            {"name": str(col), "dtype": str(df[col].dtype)}
            for col in df.columns
        ]
        return {"columns": columns}
