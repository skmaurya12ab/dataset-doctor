"""Health check schemas."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Payload returned by the application health check endpoint."""

    status: str = Field(default="ok", description="Application operational status")
