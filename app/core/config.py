"""Application configuration management using Pydantic Settings."""

from functools import lru_cache
from ipaddress import ip_network
from pathlib import Path
from typing import Literal, Optional
from pydantic import AliasChoices, Field, SecretStr, field_validator
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

    # File Ingestion & Storage Settings
    storage_backend: Literal["local", "s3"] = Field(
        default="local",
        description="Storage backend engine: 'local' (filesystem) or 's3' (S3-compatible object storage)",
    )
    upload_dir: Path = Field(
        default=Path("uploads"),
        description="Directory for uploaded datasets, staging files, and local cache",
    )
    max_upload_size_mb: int = Field(
        default=100,
        description="Maximum allowed upload file size in megabytes",
    )

    # S3-Compatible Object Storage Settings (Active when storage_backend='s3')
    s3_endpoint_url: Optional[str] = Field(
        default=None,
        description="S3 endpoint URL (e.g. Backblaze B2, MinIO, AWS S3)",
    )
    s3_bucket_name: Optional[str] = Field(
        default=None,
        description="S3 bucket name for dataset persistence",
    )
    s3_region: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("s3_region", "s3_region_name", "aws_region", "aws_default_region"),
        description="S3 region name",
    )
    s3_access_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("s3_access_key", "s3_access_key_id", "aws_access_key_id"),
        description="S3 Access Key ID / keyId",
    )
    s3_secret_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("s3_secret_key", "s3_secret_access_key", "aws_secret_access_key"),
        description="S3 Secret Access Key / applicationKey",
    )
    s3_signature_version: str = Field(
        default="s3v4",
        description="AWS signature version for S3 requests",
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
    application_base_url: str = Field(
        default="http://localhost:5173",
        description="Public frontend origin used to build verification and password-reset links",
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
    email_provider: Literal["mock", "smtp", "apps_script"] = Field(
        default="mock",
        description="Explicit email provider: mock (development/tests only), smtp, or apps_script",
    )
    email_daily_send_cap: int = Field(
        default=20,
        ge=1,
        le=80,
        description="Persistent UTC-day cap on application email dispatch attempts",
    )
    email_recipient_cooldown_seconds: int = Field(
        default=900,
        ge=60,
        le=86400,
        description="Minimum interval between auth emails to the same account",
    )
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
    apps_script_url: Optional[str] = Field(
        default=None,
        description="Deployed Apps Script web-app /exec URL; backend-only secret configuration",
    )
    apps_script_hmac_secret: Optional[SecretStr] = Field(
        default=None,
        description="High-entropy shared HMAC-SHA-256 key; backend-only secret configuration",
    )
    apps_script_timeout_seconds: float = Field(
        default=12.0,
        gt=0.0,
        le=30.0,
        description="Maximum time the async backend waits for the HTTPS Apps Script relay call",
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
    def is_s3_storage(self) -> bool:
        return self.storage_backend == "s3"

    @property
    def parsed_trusted_proxies(self) -> list[str]:
        proxies = [proxy.strip() for proxy in self.trusted_proxies.split(",") if proxy.strip()]
        normalized: list[str] = []
        for proxy in proxies:
            if proxy == "*":
                raise ValueError(
                    "Insecure trusted proxy configuration: wildcard trust is forbidden because it permits "
                    "arbitrary client-supplied forwarded IP headers."
                )
            try:
                network = ip_network(proxy, strict=False)
            except ValueError as exc:
                raise ValueError(
                    "TRUSTED_PROXIES entries must be valid IP addresses or CIDR ranges."
                ) from exc
            if network.prefixlen == 0 or network.network_address.is_unspecified:
                raise ValueError(
                    "Insecure trusted proxy configuration: all-address and unspecified networks are forbidden."
                )
            normalized.append(str(network))
        return normalized

    def validate_database_configuration(self) -> None:
        """Require the production database to use the supported async PostgreSQL driver."""
        if not self.is_production:
            return

        from urllib.parse import urlsplit

        try:
            database_url = urlsplit(self.database_url)
        except ValueError as exc:
            raise ValueError(
                "Production configuration error: DATABASE_URL must be a valid postgresql+asyncpg URL."
            ) from exc
        if (
            database_url.scheme != "postgresql+asyncpg"
            or not database_url.hostname
            or not database_url.path.strip("/")
        ):
            raise ValueError(
                "Production configuration error: DATABASE_URL must use postgresql+asyncpg and include a database host and name."
            )

    def validate_storage_configuration(self) -> None:
        """Validate storage backend configuration settings.

        Fails with clear, actionable errors without logging secrets.
        """
        if self.storage_backend == "s3":
            missing = []
            if not self.s3_endpoint_url:
                missing.append("s3_endpoint_url (S3_ENDPOINT_URL)")
            if not self.s3_bucket_name:
                missing.append("s3_bucket_name (S3_BUCKET_NAME)")
            if not self.s3_access_key:
                missing.append("s3_access_key (S3_ACCESS_KEY / S3_ACCESS_KEY_ID)")
            if not self.s3_secret_key:
                missing.append("s3_secret_key (S3_SECRET_KEY / S3_SECRET_ACCESS_KEY)")
            if missing:
                raise ValueError(
                    f"Storage configuration error: S3 backend is enabled (storage_backend='s3'), "
                    f"but the following required parameters are missing: {', '.join(missing)}. "
                    "Provide valid S3-compatible configuration."
                )

    def validate_email_configuration(self) -> None:
        """Fail closed when a selected delivery provider is missing or unsafe."""
        from urllib.parse import urlsplit

        app_url = urlsplit(self.application_base_url)
        if (
            len(self.application_base_url) > 2048
            or not self.application_base_url.isascii()
            or app_url.scheme not in {"http", "https"}
            or not app_url.hostname
            or app_url.username
            or app_url.password
            or app_url.path not in {"", "/"}
            or app_url.query
            or app_url.fragment
        ):
            raise ValueError("Email configuration error: APPLICATION_BASE_URL must be an origin without credentials or path.")

        if self.is_production and self.email_provider == "mock":
            raise ValueError(
                "Production configuration error: EMAIL_PROVIDER=mock is not allowed. "
                "Select a configured smtp or apps_script provider."
            )
        if self.is_production and not self.require_email_verification:
            raise ValueError(
                "Production configuration error: REQUIRE_EMAIL_VERIFICATION must be true."
            )

        if self.email_provider == "smtp":
            from app.core.security import validate_email_format

            if not self.smtp_host:
                raise ValueError("Email configuration error: SMTP_PROVIDER requires SMTP_HOST.")
            if bool(self.smtp_user) != bool(self.smtp_password):
                raise ValueError("Email configuration error: SMTP_USER and SMTP_PASSWORD must be set together.")
            if not self.smtp_tls:
                raise ValueError("Email configuration error: SMTP_TLS must be enabled for authentication email.")
            if (
                not self.email_from
                or not validate_email_format(self.email_from.strip())
                or (self.is_production and self.email_from.strip().lower().endswith(".local"))
            ):
                raise ValueError("Email configuration error: EMAIL_FROM must be a verified sender address.")

        if self.email_provider == "apps_script":
            if not self.apps_script_url:
                raise ValueError("Email configuration error: APPS_SCRIPT_URL is required for apps_script.")
            endpoint = urlsplit(self.apps_script_url)
            import re

            if (
                len(self.apps_script_url) > 2048
                or not self.apps_script_url.isascii()
                or endpoint.scheme != "https"
                or endpoint.hostname != "script.google.com"
                or endpoint.port not in {None, 443}
                or not re.fullmatch(r"/macros/s/[A-Za-z0-9_-]+/exec", endpoint.path)
                or endpoint.username
                or endpoint.password
                or endpoint.query
                or endpoint.fragment
            ):
                raise ValueError("Email configuration error: APPS_SCRIPT_URL must be a deployed HTTPS /exec URL.")
            if not self.apps_script_hmac_secret:
                raise ValueError("Email configuration error: APPS_SCRIPT_HMAC_SECRET is required for apps_script.")
            if len(self.apps_script_hmac_secret.get_secret_value().encode("utf-8")) < 32:
                raise ValueError("Email configuration error: APPS_SCRIPT_HMAC_SECRET must contain at least 32 bytes.")
            if app_url.scheme != "https":
                raise ValueError("Email configuration error: APPLICATION_BASE_URL must be an HTTPS origin in apps_script mode.")

        if self.is_production and self.email_provider != "mock":
            if app_url.scheme != "https":
                raise ValueError("Production configuration error: APPLICATION_BASE_URL must be an HTTPS origin.")


@lru_cache
def get_settings() -> Settings:
    """Retrieve cached application settings singleton."""
    return Settings()
