from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas import AdminLoginRequest, AdminTokenResponse
from app.security import (
    ADMIN_TOKEN_TTL_SECONDS,
    clear_failed_logins,
    create_admin_token,
    enforce_login_rate_limit,
    record_failed_login,
    require_admin,
    verify_admin_credentials,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/admin/login",
    response_model=AdminTokenResponse,
)
def admin_login(
    credentials: AdminLoginRequest,
    request: Request,
):
    client_ip = enforce_login_rate_limit(request)

    if not verify_admin_credentials(
        credentials.email,
        credentials.password,
    ):
        record_failed_login(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    clear_failed_logins(client_ip)

    return {
        "access_token": create_admin_token(),
        "token_type": "bearer",
        "expires_in": ADMIN_TOKEN_TTL_SECONDS,
    }


@router.get("/admin/me")
def admin_me(
    _admin: dict = Depends(require_admin),
):
    return {"authenticated": True}
