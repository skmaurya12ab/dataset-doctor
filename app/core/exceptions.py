"""Custom application exceptions with HTTP status mapping."""

from typing import Optional


class DatasetDoctorException(Exception):
    """Base exception for all domain errors."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class EntityNotFoundException(DatasetDoctorException):
    """Raised when a requested resource (dataset, version) does not exist."""

    def __init__(self, entity_name: str, identifier: str):
        super().__init__(f"{entity_name} '{identifier}' was not found.", status_code=404)


class OversizedFileException(DatasetDoctorException):
    """Raised when an uploaded file exceeds the configured size limit."""

    def __init__(self, max_mb: int, actual_bytes: Optional[int] = None):
        msg = f"Uploaded file exceeds maximum allowed size of {max_mb} MB."
        if actual_bytes:
            actual_mb = round(actual_bytes / (1024 * 1024), 2)
            msg += f" Received: {actual_mb} MB."
        super().__init__(msg, status_code=413)


class UnsupportedFileFormatException(DatasetDoctorException):
    """Raised when an uploaded file is not in the supported formats list."""

    def __init__(self, extension: str, supported: list[str]):
        msg = f"Unsupported file format '{extension}'. Supported formats: {', '.join(supported)}"
        super().__init__(msg, status_code=400)


class MalformedFileException(DatasetDoctorException):
    """Raised when a file cannot be parsed or is corrupted/empty."""

    def __init__(self, details: str):
        super().__init__(f"Dataset parsing error: {details}", status_code=422)


class StorageException(DatasetDoctorException):
    """Raised when a storage system or filesystem I/O operation fails."""

    def __init__(self, details: str):
        super().__init__(f"Storage I/O failure: {details}", status_code=500)


class ValidationException(DatasetDoctorException):
    """Raised when input parameters fail semantic or domain validation."""

    def __init__(self, details: str):
        super().__init__(f"Validation error: {details}", status_code=422)


class AIProviderUnavailableException(DatasetDoctorException):
    """Raised when the AI provider cannot be reached or times out."""

    def __init__(self, details: str = "AI interpretation provider is currently unreachable"):
        super().__init__(f"Service Unavailable: {details}", status_code=503)


class AIProviderOutputException(DatasetDoctorException):
    """Raised when the AI provider returns malformed, unparseable, or invalid output."""

    def __init__(self, details: str = "Invalid output received from AI provider"):
        super().__init__(f"Bad Gateway: {details}", status_code=502)


class AIRefusalException(DatasetDoctorException):
    """Raised when the AI provider explicitly refuses to complete the request."""

    def __init__(self, refusal_reason: str):
        super().__init__(f"AI Provider Refusal: {refusal_reason}", status_code=502)


class InvalidTransformationException(DatasetDoctorException):
    """Raised when proposed transformation violates allowlist or parameter boundaries."""

    def __init__(self, details: str):
        super().__init__(f"Invalid Transformation: {details}", status_code=400)


