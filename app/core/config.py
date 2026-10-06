"""Application configuration management using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core settings for Dataset Doctor.
    
    Reads from environment variables and an optional .env file.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application Metadata
    app_name: str = Field(default="Dataset Doctor", description="Name of the application")
    environment: Literal["development", "staging", "production", "testing"] = Field(
        default="development",
        description="Current runtime environment",
    )
    debug: bool = Field(default=False, description="Enable debug mode")

    # Database Settings
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/dataset_doctor",
        description="Async SQLAlchemy database connection string",
    )

    # File Ingestion & Storage
    upload_dir: Path = Field(
        default=Path("uploads"),
        description="Directory for uploaded datasets and artifacts",
    )
    max_upload_size_mb: int = Field(
        default=100,
        description="Maximum allowed upload file size in megabytes",
    )

    # AI Interpretation Provider Settings
    openai_api_key: Optional[str] = Field(
        default=None,
        description="API key for OpenAI-compatible interpretation provider",
    )
    openai_model: str = Field(
        default="gpt-4o-2024-08-06",
        description="Target model for structured reasoning and interpretation",
    )
    openai_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        description="Timeout in seconds for AI provider requests",
    )
    openai_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for transient AI provider failures",
    )
    openai_retry_backoff: float = Field(
        default=1.5,
        gt=0.0,
        description="Exponential backoff factor for retries",
    )
    openai_max_input_tokens: int = Field(
        default=3500,
        ge=500,
        le=16000,
        description="Token budget cap for findings digest sent to the LLM",
    )
    openai_max_output_tokens: int = Field(
        default=2000,
        ge=100,
        le=8000,
        description="Maximum output tokens for AI structured completions",
    )

    # Logging Settings
    log_level: str = Field(
        default="INFO",
        description="Application logging verbosity level",
    )

    # V1 Background Worker Settings
    max_worker_threads: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Maximum concurrent threads in V1 ThreadPoolJobRunner",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_val = value.upper()
        if upper_val not in valid_levels:
            raise ValueError(f"Invalid log level '{value}'. Must be one of {valid_levels}")
        return upper_val

    @property
    def max_upload_size_bytes(self) -> int:
        """Derived upload limit in bytes."""
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Retrieve cached application settings singleton."""
    return Settings()
