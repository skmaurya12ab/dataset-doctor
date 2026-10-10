"""Pydantic schemas for authentication, registration, session, and password management."""

from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.security import validate_email_format


class UserRegisterRequest(BaseModel):
    """Payload for user account self-registration."""

    email: str = Field(description="User email address")
    password: str = Field(min_length=8, max_length=128, description="Plaintext password (min 8 characters)")

    @field_validator("email")
    @classmethod
    def normalize_email_address(cls, v: str) -> str:
        clean = v.strip().lower()
        if not validate_email_format(clean):
            raise ValueError("Invalid email address format.")
        return clean

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if len(v) > 128:
            raise ValueError("Password cannot exceed 128 characters.")
        return v


class UserLoginRequest(BaseModel):
    """Payload for standard email and password authentication."""

    email: str = Field(description="User registered email address")
    password: str = Field(description="Account password")

    @field_validator("email")
    @classmethod
    def normalize_email_address(cls, v: str) -> str:
        clean = v.strip().lower()
        if not validate_email_format(clean):
            raise ValueError("Invalid email address format.")
        return clean


class UserResponse(BaseModel):
    """Safe public representation of an authenticated user."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_active: bool
    is_verified: bool
    role: str
    created_at: datetime


class LoginResponse(BaseModel):
    """Response returned upon successful authentication."""

    user: UserResponse
    message: str = "Authentication successful"
    csrf_token: str


class VerifyEmailRequest(BaseModel):
    """Payload for verifying an account email address via one-time token."""

    token: str = Field(min_length=10, description="Verification token received via email")


class ForgotPasswordRequest(BaseModel):
    """Payload for initiating a password reset workflow."""

    email: str = Field(description="User registered email address")

    @field_validator("email")
    @classmethod
    def normalize_email_address(cls, v: str) -> str:
        clean = v.strip().lower()
        if not validate_email_format(clean):
            raise ValueError("Invalid email address format.")
        return clean


class ResetPasswordRequest(BaseModel):
    """Payload for completing password reset with an issued single-use token."""

    token: str = Field(min_length=10, description="Single-use password reset token")
    new_password: str = Field(min_length=8, max_length=128, description="New password (min 8 characters)")

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v


class MessageResponse(BaseModel):
    """Generic status response for asynchronous or security-neutral operations."""

    message: str
    success: bool = True
