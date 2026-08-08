from __future__ import annotations

import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from redis.asyncio import Redis
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_redis
from app.models.database import OtpCode, User, get_db_session
from app.models.schemas import UserResponse
from app.utils.email import send_otp_email


ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
OTP_EXPIRE_MINUTES = 10
OTP_RATE_LIMIT_SECONDS = 60
REFRESH_COOKIE_NAME = "refresh_token"

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
    bcrypt__ident="2b",
)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

oauth = OAuth()

oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

oauth.register(
    name="github",
    client_id=settings.GITHUB_CLIENT_ID,
    client_secret=settings.GITHUB_CLIENT_SECRET,
    api_base_url="https://api.github.com/",
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    client_kwargs={"scope": "user:email"},
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _validate_email(email: str) -> None:
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format")


def _validate_password_strength(password: str) -> None:
    if len(password) < 8 or not any(ch.isdigit() for ch in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters and include at least one number",
        )


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _generate_otp_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def _encode_token(user: User, token_type: Literal["access", "refresh"], expires_delta: timedelta) -> str:
    now = _utc_now()
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "email": user.email,
        "type": token_type,
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user: User) -> str:
    return _encode_token(user, ACCESS_TOKEN_TYPE, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(user: User) -> str:
    return _encode_token(user, REFRESH_TOKEN_TYPE, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def decode_token(token: str, expected_type: Literal["access", "refresh"] | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], options={"verify_aud": False})
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    token_type = payload.get("type")
    if expected_type and token_type != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    return payload


async def _ensure_not_blocklisted(redis: Redis, jti: str | None) -> None:
    if not jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    blocked = await redis.get(f"jwt_blocklist:{jti}")
    if blocked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")


async def _enforce_otp_rate_limit(redis: Redis, user_id: UUID, purpose: Literal["verify_email", "login"]) -> None:
    key = f"otp_rate:{user_id}:{purpose}"
    if await redis.get(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Please wait before requesting another code")
    await redis.set(key, "1", ex=OTP_RATE_LIMIT_SECONDS)


async def _load_user_by_email(db: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == _normalize_email(email))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _create_otp_code(
    db: AsyncSession,
    user: User,
    purpose: Literal["verify_email", "login"],
) -> str:
    code = _generate_otp_code()
    otp = OtpCode(
        user_id=user.id,
        code=_hash_password(code),
        purpose=purpose,
        expires_at=_utc_now() + timedelta(minutes=OTP_EXPIRE_MINUTES),
    )
    db.add(otp)
    return code


def _validate_user_for_login(user: User) -> None:
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive")
    if not user.is_verified:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not verified")


def _auth_payload(user: User) -> dict[str, Any]:
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": UserResponse.model_validate(user),
    }


class AuthService:
    @staticmethod
    async def register(
        db: AsyncSession,
        redis: Redis,
        full_name: str,
        email: str,
        password: str,
    ) -> dict[str, str]:
        normalized_email = _normalize_email(email)
        _validate_email(normalized_email)
        _validate_password_strength(password)

        existing_user = await _load_user_by_email(db, normalized_email)
        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

        user = User(
            email=normalized_email,
            full_name=full_name,
            hashed_password=_hash_password(password),
            is_verified=False,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        await _enforce_otp_rate_limit(redis, user.id, "verify_email")
        code = await _create_otp_code(db, user, "verify_email")
        await db.commit()

        await send_otp_email(to_email=normalized_email, code=code, purpose="verify_email")
        return {"message": "Check your email for a verification code"}

    @staticmethod
    async def verify_otp(
        db: AsyncSession,
        email: str,
        code: str,
        purpose: Literal["verify_email", "login"],
    ) -> dict[str, Any]:
        user = await _load_user_by_email(db, email)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OTP")

        stmt = (
            select(OtpCode)
            .where(
                OtpCode.user_id == user.id,
                OtpCode.purpose == purpose,
                OtpCode.used_at.is_(None),
                OtpCode.expires_at > _utc_now(),
            )
            .order_by(desc(OtpCode.created_at))
            .limit(1)
        )
        result = await db.execute(stmt)
        otp = result.scalar_one_or_none()

        if not otp or not _verify_password(code, otp.code):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OTP")

        otp.used_at = _utc_now()
        if purpose == "verify_email":
            user.is_verified = True

        _validate_user_for_login(user)
        await db.commit()
        await db.refresh(user)

        return _auth_payload(user)

    @staticmethod
    async def login_with_password(db: AsyncSession, email: str, password: str) -> dict[str, Any]:
        user = await _load_user_by_email(db, email)
        if not user or not user.hashed_password:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        if not _verify_password(password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        _validate_user_for_login(user)
        return _auth_payload(user)

    @staticmethod
    async def request_login_otp(db: AsyncSession, redis: Redis, email: str) -> dict[str, str]:
        user = await _load_user_by_email(db, email)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        _validate_user_for_login(user)
        await _enforce_otp_rate_limit(redis, user.id, "login")

        code = await _create_otp_code(db, user, "login")
        await db.commit()

        await send_otp_email(to_email=user.email, code=code, purpose="login")
        return {"message": "Check your email for a verification code"}

    @staticmethod
    async def refresh(db: AsyncSession, redis: Redis, refresh_token: str) -> dict[str, Any]:
        payload = decode_token(refresh_token, expected_type=REFRESH_TOKEN_TYPE)
        await _ensure_not_blocklisted(redis, payload.get("jti"))

        user_id = payload["sub"]
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        _validate_user_for_login(user)

        exp = int(payload.get("exp", 0))
        now = int(_utc_now().timestamp())
        ttl = max(exp - now, 0)
        if ttl > 0:
            await redis.set(f"jwt_blocklist:{payload['jti']}", "1", ex=ttl)

        return _auth_payload(user)

    @staticmethod
    async def logout(redis: Redis, token: str) -> None:
        payload = decode_token(token)
        jti = payload.get("jti")
        if not jti:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        exp = int(payload.get("exp", 0))
        now = int(_utc_now().timestamp())
        ttl = max(exp - now, 0)
        if ttl > 0:
            await redis.set(f"jwt_blocklist:{jti}", "1", ex=ttl)

    @staticmethod
    async def update_me(db: AsyncSession, user: User, full_name: str | None, avatar_url: str | None) -> User:
        if full_name is not None:
            user.full_name = full_name
        if avatar_url is not None:
            user.avatar_url = avatar_url
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def sso_login(
        db: AsyncSession,
        provider: Literal["google", "github"],
        subject: str,
        email: str,
        full_name: str | None,
        avatar_url: str | None,
    ) -> dict[str, Any]:
        normalized_email = _normalize_email(email)
        _validate_email(normalized_email)

        stmt = select(User).where(User.sso_provider == provider, User.sso_subject == subject)
        existing_by_subject = (await db.execute(stmt)).scalar_one_or_none()
        if existing_by_subject:
            _validate_user_for_login(existing_by_subject)
            return _auth_payload(existing_by_subject)

        existing_user = await _load_user_by_email(db, normalized_email)
        if existing_user:
            existing_user.sso_provider = provider
            existing_user.sso_subject = subject
            existing_user.is_verified = True
            if full_name and not existing_user.full_name:
                existing_user.full_name = full_name
            if avatar_url:
                existing_user.avatar_url = avatar_url
            await db.commit()
            await db.refresh(existing_user)
            _validate_user_for_login(existing_user)
            return _auth_payload(existing_user)

        user = User(
            email=normalized_email,
            full_name=full_name,
            hashed_password=None,
            is_verified=True,
            is_active=True,
            sso_provider=provider,
            sso_subject=subject,
            avatar_url=avatar_url,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        return _auth_payload(user)


def set_refresh_cookie(response: Any, refresh_token: str) -> None:
    max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=max_age,
        expires=max_age,
        path="/auth",
    )


def clear_refresh_cookie(response: Any) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/auth")


def _provider_or_400(provider: str) -> Literal["google", "github"]:
    if provider not in {"google", "github"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported SSO provider")
    return provider


def _validate_provider_credentials(provider: Literal["google", "github"]) -> None:
    if provider == "google" and (not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google SSO is not configured")
    if provider == "github" and (not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GitHub SSO is not configured")


async def get_sso_redirect(request: Request, provider: str):
    provider_name = _provider_or_400(provider)
    _validate_provider_credentials(provider_name)
    client = oauth.create_client(provider_name)
    redirect_uri = f"{settings.SSO_REDIRECT_BASE}/auth/sso/{provider_name}/callback"
    return await client.authorize_redirect(request, redirect_uri)


async def sso_callback_auth(
    request: Request,
    db: AsyncSession,
    provider: str,
) -> dict[str, Any]:
    provider_name = _provider_or_400(provider)
    _validate_provider_credentials(provider_name)
    client = oauth.create_client(provider_name)
    token = await client.authorize_access_token(request)

    if provider_name == "google":
        user_info = token.get("userinfo")
        if not user_info:
            user_info = await client.parse_id_token(request, token)
        if not user_info:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to fetch Google profile")

        email = user_info.get("email")
        subject = user_info.get("sub")
        full_name = user_info.get("name")
        avatar_url = user_info.get("picture")
    else:
        profile_response = await client.get("user", token=token)
        profile = profile_response.json()

        email = profile.get("email")
        if not email:
            emails_response = await client.get("user/emails", token=token)
            emails = emails_response.json()
            primary_verified = next(
                (item for item in emails if item.get("primary") and item.get("verified")),
                None,
            )
            if primary_verified:
                email = primary_verified.get("email")

        subject = str(profile.get("id")) if profile.get("id") is not None else None
        full_name = profile.get("name") or profile.get("login")
        avatar_url = profile.get("avatar_url")

    if not email or not subject:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to determine SSO account identity")

    return await AuthService.sso_login(
        db=db,
        provider=provider_name,
        subject=str(subject),
        email=email,
        full_name=full_name,
        avatar_url=avatar_url,
    )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> User:
    payload = decode_token(token, expected_type=ACCESS_TOKEN_TYPE)
    await _ensure_not_blocklisted(redis, payload.get("jti"))

    user_id = payload.get("sub")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    _validate_user_for_login(user)
    return user
