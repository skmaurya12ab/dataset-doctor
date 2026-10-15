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

    # Authentication & Session Security Settings
    session_cookie_name: str = Field(
        default="dd_session",
        description="Name of the HTTP-only session cookie",
    )
    session_max_age_seconds: int = Field(
        default=7 * 24 * 3600,  # 7 days
        gt=0,
        description="Session time-to-live in seconds",
    )
    cookie_secure: Optional[bool] = Field(
        default=None,
        description="Enforce Secure flag on cookies. Defaults to True in production.",
    )
    cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="lax",
        description="SameSite cookie policy",
    )
    require_email_verification: bool = Field(
        default=False,
        description="Whether email verification is required to log in and access datasets",
    )
    email_verification_token_expire_hours: int = Field(
        default=24,
        gt=0,
        description="Validity window for email verification tokens in hours",
    )
    password_reset_token_expire_hours: int = Field(
        default=1,
        gt=0,
        description="Validity window for password reset tokens in hours",
    )
    allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:8000,http://127.0.0.1:5173,http://127.0.0.1:8000",
        description="Comma-separated list of allowed CORS origins",
    )
    enable_api_docs: bool = Field(
        default=False,
        description="Explicitly expose OpenAPI/Swagger documentation in production",
    )

    # Ingress & Trusted Proxy Settings
    trusted_proxies: str = Field(
        default="127.0.0.1,::1",
        description="Comma-separated list of trusted reverse proxy IP addresses",
    )

    # User Account Resource Quotas (Abuse Prevention)
    max_datasets_per_user: int = Field(
        default=20,
        ge=1,
        description="Maximum stored datasets per user account",
    )
    max_cumulative_storage_mb_per_user: int = Field(
        default=500,
        ge=1,
        description="Maximum cumulative file and Parquet storage per user in megabytes",
    )
    max_concurrent_analysis_jobs_per_user: int = Field(
        default=2,
        ge=1,
        description="Maximum concurrent active (PENDING or RUNNING) analysis jobs per user",
    )
    rate_limit_analysis_triggers_per_minute: int = Field(
        default=10,
        ge=1,
        description="Maximum analysis triggers per minute per user",
    )
    rate_limit_ai_explanations_per_minute: int = Field(
        default=20,
        ge=1,
        description="Maximum AI explanation requests per minute per user",
    )
    rate_limit_ai_plans_per_minute: int = Field(
        default=10,
        ge=1,
        description="Maximum AI remediation plan generation requests per minute per user",
    )
    rate_limit_remediations_per_minute: int = Field(
        default=10,
        ge=1,
        description="Maximum remediation applications per minute per user",
    )

    # Email & Notification Settings
    smtp_host: Optional[str] = Field(
        default=None,
        description="SMTP host for delivering verification and reset emails",
    )
    smtp_port: int = Field(
        default=587,
        description="SMTP server port",
    )
    smtp_user: Optional[str] = Field(
        default=None,
        description="SMTP username",
    )
    smtp_password: Optional[str] = Field(
        default=None,
        description="SMTP password",
    )
    smtp_tls: bool = Field(
        default=True,
        description="Use STARTTLS for SMTP connections",
    )
    email_from: str = Field(
        default="noreply@datasetdoctor.local",
        description="From address for system emails",
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
    def max_cumulative_storage_bytes(self) -> int:
        """Derived cumulative storage limit in bytes per user."""
        return self.max_cumulative_storage_mb_per_user * 1024 * 1024

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_cookie_secure(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.is_production

    @property
    def parsed_allowed_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]
        if self.is_production and "*" in origins:
            raise ValueError("Wildcard origin '*' is forbidden in production when credentials are enabled.")
        return origins

    @property
    def parsed_trusted_proxies(self) -> list[str]:
        return [proxy.strip() for proxy in self.trusted_proxies.split(",") if proxy.strip()]

    def validate_production_smtp(self) -> None:
        """Ensure SMTP is configured if email verification is mandatory in production.

        Fails with clear configuration errors without logging password secrets.
        """
        if self.is_production and self.require_email_verification:
            if not self.smtp_host:
                raise ValueError(
                    "Production configuration error: 'require_email_verification' is enabled "
                    "but 'smtp_host' is not configured. Provide SMTP_HOST and credentials."
                )
            if not self.email_from:
                raise ValueError(
                    "Production configuration error: 'email_from' sender address must be provided."
                )


@lru_cache
def get_settings() -> Settings:
    """Retrieve cached application settings singleton."""
    return Settings()
