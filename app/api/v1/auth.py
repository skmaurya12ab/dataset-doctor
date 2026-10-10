"""Authentication API router: registration, credentials login, session management, and password reset."""

from typing import Optional
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSessionDep, get_current_user
from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationException
from app.core.logging import get_logger
from app.core.rate_limit import rate_limiter
from app.core.security import generate_token
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginResponse,
    MessageResponse,
    ResetPasswordRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.services.auth_service import AuthService, get_auth_service

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_client_ip(request: Request) -> str:
    """Safely extract remote client IP address for rate limiting."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user account",
)
async def register(
    req: UserRegisterRequest,
    request: Request,
    db: DBSessionDep,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Create a new user account with Argon2id password hashing and dispatch verification email."""
    client_ip = get_client_ip(request)
    rate_limiter.enforce(f"register:{client_ip}", max_requests=10, window_seconds=60, action_name="Registration")

    user = await auth_service.register_user(db=db, req=req)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and establish server-side session",
)
async def login(
    req: UserLoginRequest,
    request: Request,
    response: Response,
    db: DBSessionDep,
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    """Authenticate email and password, issue cryptographically random session token, and set HttpOnly cookie."""
    client_ip = get_client_ip(request)
    rate_limiter.enforce(f"login:{client_ip}", max_requests=10, window_seconds=60, action_name="Login")

    user = await auth_service.authenticate_user(db=db, req=req)

    user_agent = request.headers.get("User-Agent")
    session, raw_token = await auth_service.create_session(
        db=db,
        user_id=user.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    # Establish HttpOnly session cookie
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.is_cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )

    # Issue CSRF token for defense in depth
    csrf_token = generate_token(16)
    response.set_cookie(
        key="dd_csrf",
        value=csrf_token,
        max_age=settings.session_max_age_seconds,
        httponly=False,
        secure=settings.is_cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )

    return LoginResponse(
        user=UserResponse.model_validate(user),
        message="Authentication successful",
        csrf_token=csrf_token,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Invalidate active session and clear cookies",
)
async def logout(
    request: Request,
    response: Response,
    db: DBSessionDep,
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    """Revoke session on server and instruct browser to delete session cookies."""
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()

    if raw_token:
        await auth_service.invalidate_session(db=db, raw_token=raw_token)

    response.delete_cookie(key=settings.session_cookie_name, path="/")
    response.delete_cookie(key="dd_csrf", path="/")

    return MessageResponse(message="Logged out successfully")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user identity",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Retrieve the currently authenticated user's profile and account status."""
    return UserResponse.model_validate(current_user)


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify user account via token",
)
async def verify_email(
    req: VerifyEmailRequest,
    request: Request,
    db: DBSessionDep,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """Consume single-use email verification token and activate account status."""
    client_ip = get_client_ip(request)
    rate_limiter.enforce(f"verify_email:{client_ip}", max_requests=10, window_seconds=60, action_name="Email verification")

    await auth_service.verify_email(db=db, token_str=req.token)
    return MessageResponse(message="Email address verified successfully.")


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request password reset token",
)
async def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    db: DBSessionDep,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """Request password reset link. Generic response returned regardless of account existence."""
    client_ip = get_client_ip(request)
    rate_limiter.enforce(f"forgot_pw:{client_ip}", max_requests=5, window_seconds=60, action_name="Password reset request")

    await auth_service.request_password_reset(db=db, email=req.email)
    return MessageResponse(
        message="If an account exists with this email address, password reset instructions have been sent."
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset account password via token",
)
async def reset_password(
    req: ResetPasswordRequest,
    request: Request,
    db: DBSessionDep,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """Consume single-use password reset token, update password, and revoke all sessions."""
    client_ip = get_client_ip(request)
    rate_limiter.enforce(f"reset_pw:{client_ip}", max_requests=10, window_seconds=60, action_name="Password reset")

    await auth_service.reset_password(db=db, token_str=req.token, new_password=req.new_password)
    return MessageResponse(
        message="Password has been reset successfully. You may now log in with your new password."
    )
