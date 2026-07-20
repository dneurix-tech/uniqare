import base64
import hashlib
import hmac
import json
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, Request, status


ADMIN_TOKEN_TTL_SECONDS = int(
    os.getenv("ADMIN_TOKEN_TTL_SECONDS", "43200")
)
ORDER_PAYMENT_TOKEN_TTL_SECONDS = int(
    os.getenv("ORDER_PAYMENT_TOKEN_TTL_SECONDS", "14400")
)
LOGIN_WINDOW_SECONDS = int(
    os.getenv("ADMIN_LOGIN_WINDOW_SECONDS", "900")
)
LOGIN_MAX_FAILURES = int(
    os.getenv("ADMIN_LOGIN_MAX_FAILURES", "5")
)

_failed_logins: dict[str, deque[float]] = defaultdict(deque)
_failed_logins_lock = threading.Lock()
_public_requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_public_requests_lock = threading.Lock()




def legacy_security_migration_enabled() -> bool:
    return os.getenv(
        "ALLOW_LEGACY_UNAUTHENTICATED_ADMIN",
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _token_secret() -> bytes:
    secret = os.getenv("ADMIN_TOKEN_SECRET", "").strip()

    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Admin security is not configured. "
                "Set ADMIN_TOKEN_SECRET to at least 32 characters."
            ),
        )

    return secret.encode("utf-8")


def _sign(encoded_payload: str) -> str:
    signature = hmac.new(
        _token_secret(),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _base64url_encode(signature)


def create_signed_token(payload: dict[str, Any], ttl_seconds: int) -> str:
    now = int(time.time())
    token_payload = {
        **payload,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    raw_payload = json.dumps(
        token_payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded_payload = _base64url_encode(raw_payload)
    return f"{encoded_payload}.{_sign(encoded_payload)}"


def decode_signed_token(token: str) -> dict[str, Any]:
    try:
        encoded_payload, received_signature = token.split(".", 1)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from error

    expected_signature = _sign(encoded_payload)

    if not hmac.compare_digest(
        received_signature,
        expected_signature,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    try:
        payload = json.loads(
            _base64url_decode(encoded_payload).decode("utf-8")
        )
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from error

    expires_at = payload.get("exp")

    if not isinstance(expires_at, int) or expires_at <= int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
        )

    return payload


def create_admin_token() -> str:
    return create_signed_token(
        {
            "typ": "admin",
            "sub": "uniqare-admin",
        },
        ADMIN_TOKEN_TTL_SECONDS,
    )


def create_order_payment_token(order_id: int) -> str:
    return create_signed_token(
        {
            "typ": "order_payment",
            "order_id": int(order_id),
        },
        ORDER_PAYMENT_TOKEN_TTL_SECONDS,
    )


def verify_admin_credentials(email: str, password: str) -> bool:
    configured_email = os.getenv("ADMIN_LOGIN_EMAIL", "").strip().lower()
    configured_password = os.getenv("ADMIN_LOGIN_PASSWORD", "")

    if not configured_email or not configured_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Admin login is not configured. "
                "Set ADMIN_LOGIN_EMAIL and ADMIN_LOGIN_PASSWORD."
            ),
        )

    email_matches = hmac.compare_digest(
        email.strip().lower().encode("utf-8"),
        configured_email.encode("utf-8"),
    )
    password_matches = hmac.compare_digest(
        password.encode("utf-8"),
        configured_password.encode("utf-8"),
    )

    return email_matches and password_matches


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")

    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()

    if request.client:
        return request.client.host

    return "unknown"


def enforce_login_rate_limit(request: Request) -> str:
    client_ip = _client_ip(request)
    cutoff = time.time() - LOGIN_WINDOW_SECONDS

    with _failed_logins_lock:
        attempts = _failed_logins[client_ip]

        while attempts and attempts[0] < cutoff:
            attempts.popleft()

        if len(attempts) >= LOGIN_MAX_FAILURES:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Too many failed login attempts. "
                    "Please try again later."
                ),
            )

    return client_ip




def enforce_public_rate_limit(
    request: Request,
    action: str,
    max_requests: int,
    window_seconds: int,
) -> None:
    client_ip = _client_ip(request)
    key = (action, client_ip)
    now = time.time()
    cutoff = now - window_seconds

    with _public_requests_lock:
        attempts = _public_requests[key]

        while attempts and attempts[0] < cutoff:
            attempts.popleft()

        if len(attempts) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )

        attempts.append(now)


def record_failed_login(client_ip: str) -> None:
    with _failed_logins_lock:
        _failed_logins[client_ip].append(time.time())


def clear_failed_logins(client_ip: str) -> None:
    with _failed_logins_lock:
        _failed_logins.pop(client_ip, None)


def _get_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "").strip()

    if not authorization:
        return None

    scheme, separator, token = authorization.partition(" ")

    if not separator or scheme.lower() != "bearer" or not token.strip():
        return None

    return token.strip()


def require_admin(
    request: Request,
) -> dict[str, Any]:
    token = _get_bearer_token(request)

    if not token:
        if legacy_security_migration_enabled():
            return {"typ": "legacy-admin-migration"}

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_signed_token(token)

    if payload.get("typ") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is required",
        )

    return payload


def authorize_order_payment(
    request: Request,
    order_id: int,
) -> str:
    bearer_token = _get_bearer_token(request)

    if bearer_token:
        payload = decode_signed_token(bearer_token)

        if payload.get("typ") == "admin":
            return "admin"

    order_token = request.headers.get("x-order-token", "").strip()

    if not order_token:
        if legacy_security_migration_enabled():
            return "legacy-customer"

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid order payment token is required",
        )

    payload = decode_signed_token(order_token)

    if (
        payload.get("typ") != "order_payment"
        or payload.get("order_id") != int(order_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This payment token does not match the order",
        )

    return "customer"

