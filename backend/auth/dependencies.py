import logging
import os
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db.models import Profile
from backend.env import is_local_env, load_backend_env
from backend.services.request_timing import timed_stage

logger = logging.getLogger(__name__)
AUTH_CACHE_TTL_SECONDS = 60
AUTH_HTTP_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class TokenIdentity:
    user_id: str | None
    email: str | None
    supabase_status: int | None


_auth_cache: dict[str, tuple[float, TokenIdentity]] = {}
_auth_inflight: dict[str, Future[TokenIdentity]] = {}
_auth_lock = threading.Lock()


def _token_cache_key(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def clear_auth_cache() -> None:
    with _auth_lock:
        _auth_cache.clear()
        _auth_inflight.clear()


def _get_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        return None

    scheme, _, token = auth_header.partition(" ")

    if scheme.lower() != "bearer" or not token.strip():
        return None

    return token.strip()


def _supabase_auth_headers(token: str) -> dict[str, str]:
    anon_key = os.getenv("SUPABASE_ANON_KEY")

    if not anon_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase environment variables are not configured",
        )

    return {
        "Authorization": f"Bearer {token}",
        "apikey": anon_key,
    }


def _fetch_user_from_token(token: str) -> TokenIdentity:
    supabase_url = os.getenv("SUPABASE_URL")

    if not supabase_url:
        return TokenIdentity(None, None, None)

    url = f"{supabase_url.rstrip('/')}/auth/v1/user"

    try:
        response = httpx.get(
            url,
            headers=_supabase_auth_headers(token),
            timeout=AUTH_HTTP_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError:
        return TokenIdentity(None, None, None)

    if response.status_code != status.HTTP_200_OK:
        return TokenIdentity(None, None, response.status_code)

    try:
        payload = response.json()
    except ValueError:
        return TokenIdentity(None, None, response.status_code)

    user_id = payload.get("id")
    email = payload.get("email")

    if not isinstance(user_id, str):
        return TokenIdentity(None, email if isinstance(email, str) else None, response.status_code)

    return TokenIdentity(user_id, email if isinstance(email, str) else None, response.status_code)


def _user_from_token(token: str) -> tuple[str | None, str | None, int | None]:
    cache_key = _token_cache_key(token)
    now = time.monotonic()
    with _auth_lock:
        cached = _auth_cache.get(cache_key)
        if cached and cached[0] > now:
            identity = cached[1]
            return identity.user_id, identity.email, identity.supabase_status

        future = _auth_inflight.get(cache_key)
        leader = future is None
        if leader:
            future = Future()
            _auth_inflight[cache_key] = future

    if not leader:
        identity = future.result(timeout=AUTH_HTTP_TIMEOUT_SECONDS + 0.5)
        return identity.user_id, identity.email, identity.supabase_status

    try:
        identity = _fetch_user_from_token(token)
        if identity.user_id is not None:
            with _auth_lock:
                _auth_cache[cache_key] = (time.monotonic() + AUTH_CACHE_TTL_SECONDS, identity)
        future.set_result(identity)
        return identity.user_id, identity.email, identity.supabase_status
    except BaseException as exc:
        future.set_exception(exc)
        raise
    finally:
        with _auth_lock:
            _auth_inflight.pop(cache_key, None)


def _default_username(email: str | None, profile_id: UUID) -> str:
    if email and "@" in email:
        return email.split("@", 1)[0]

    return f"user-{str(profile_id)[:8]}"


def _log_local_auth_failure(
    *,
    request: Request,
    token: str | None,
    supabase_status: int | None = None,
    profile_found: bool | None = None,
    supabase_user_id: str | None = None,
    supabase_email: str | None = None,
    profile_lookup: str | None = None,
) -> None:
    if not is_local_env():
        return

    logger.warning(
        "Local auth failure debug: auth_header_present=%s "
        "supabase_url_present=%s supabase_anon_key_present=%s "
        "supabase_service_role_key_present=%s supabase_user_status=%s "
        "supabase_user_id_present=%s supabase_email_present=%s "
        "profile_lookup=%s profile_found=%s path=%s",
        bool(token),
        bool(os.getenv("SUPABASE_URL")),
        bool(os.getenv("SUPABASE_ANON_KEY")),
        bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
        supabase_status,
        bool(supabase_user_id),
        bool(supabase_email),
        profile_lookup,
        profile_found,
        request.url.path,
    )


def _token_from_credentials_or_header(request: Request, credentials=None) -> str | None:
    credential_token = getattr(credentials, "credentials", None)

    if credential_token:
        return credential_token.strip()

    return _get_bearer_token(request)


def get_current_user(
    request: Request,
    credentials=None,
    db: Session = Depends(get_db),
) -> Profile:
    load_backend_env()

    token = _token_from_credentials_or_header(request, credentials)

    if token is None:
        _log_local_auth_failure(request=request, token=None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_ANON_KEY"):
        _log_local_auth_failure(request=request, token=token)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase environment variables are not configured",
        )

    with timed_stage("auth"):
        user_id, email, supabase_status = _user_from_token(token)

    if user_id is None:
        _log_local_auth_failure(
            request=request,
            token=token,
            supabase_status=supabase_status,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    try:
        profile_id = UUID(user_id)
    except ValueError:
        _log_local_auth_failure(
            request=request,
            token=token,
            supabase_status=supabase_status,
            supabase_user_id=user_id,
            supabase_email=email,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authenticated user",
        )

    with timed_stage("profile_lookup"):
        profile = db.query(Profile).filter(Profile.id == profile_id).first()

    if profile is not None:
        return profile

    if email:
        with timed_stage("profile_lookup"):
            profile = db.query(Profile).filter(Profile.email == email).first()

        if profile is not None:
            return profile

    profile = Profile(
        id=profile_id,
        email=email or f"{profile_id}@unknown.local",
        username=_default_username(email, profile_id),
    )

    with timed_stage("profile_create"):
        db.add(profile)
        db.commit()
        db.refresh(profile)

    return profile
