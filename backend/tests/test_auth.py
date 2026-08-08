from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.database import OtpCode, User
from app.services import auth_service
from app.services.auth_service import AuthService, create_access_token, create_refresh_token, decode_token, sso_callback_auth


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _create_verified_user(test_db, email: str = "user@example.com") -> User:
    user = User(
        email=email,
        full_name="Test User",
        hashed_password=auth_service._hash_password("Password1"),
        is_verified=True,
        is_active=True,
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


async def test_register_verify_otp_login(test_db, test_redis, monkeypatch):
    monkeypatch.setattr(auth_service, "send_otp_email", AsyncMock())
    monkeypatch.setattr(auth_service, "_generate_otp_code", lambda: "123456")

    register_result = await AuthService.register(
        db=test_db,
        redis=test_redis,
        full_name="Alice",
        email="alice@example.com",
        password="Secure123",
    )
    assert "verification code" in register_result["message"].lower()

    verify_result = await AuthService.verify_otp(
        db=test_db,
        email="alice@example.com",
        code="123456",
        purpose="verify_email",
    )
    assert verify_result["access_token"]
    assert verify_result["refresh_token"]
    assert verify_result["user"].is_verified is True

    login_result = await AuthService.login_with_password(db=test_db, email="alice@example.com", password="Secure123")
    assert login_result["access_token"]
    assert login_result["user"].email == "alice@example.com"


async def test_otp_expiry_and_reuse_prevention(test_db, test_redis, monkeypatch):
    monkeypatch.setattr(auth_service, "send_otp_email", AsyncMock())
    monkeypatch.setattr(auth_service, "_generate_otp_code", lambda: "654321")

    await AuthService.register(
        db=test_db,
        redis=test_redis,
        full_name="Bob",
        email="bob@example.com",
        password="Secure123",
    )

    bob = (await test_db.execute(select(User).where(User.email == "bob@example.com"))).scalar_one()
    otp = (
        (
            await test_db.execute(
                select(OtpCode).where(OtpCode.user_id == bob.id, OtpCode.purpose == "verify_email").order_by(OtpCode.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert otp is not None

    otp.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await test_db.commit()

    with pytest.raises(HTTPException):
        await AuthService.verify_otp(db=test_db, email="bob@example.com", code="654321", purpose="verify_email")

    monkeypatch.setattr(auth_service, "_generate_otp_code", lambda: "111111")
    await AuthService.register(
        db=test_db,
        redis=test_redis,
        full_name="Carol",
        email="carol@example.com",
        password="Secure123",
    )

    await AuthService.verify_otp(db=test_db, email="carol@example.com", code="111111", purpose="verify_email")
    with pytest.raises(HTTPException):
        await AuthService.verify_otp(db=test_db, email="carol@example.com", code="111111", purpose="verify_email")


async def test_jwt_refresh_and_logout_blocklist(test_db, test_redis):
    user = await _create_verified_user(test_db, email="tokens@example.com")

    refresh_token = create_refresh_token(user)
    refreshed = await AuthService.refresh(db=test_db, redis=test_redis, refresh_token=refresh_token)
    assert refreshed["access_token"]
    assert refreshed["refresh_token"]

    refresh_payload = decode_token(refresh_token, expected_type="refresh")
    assert await test_redis.get(f"jwt_blocklist:{refresh_payload['jti']}") == "1"

    access_token = create_access_token(user)
    await AuthService.logout(redis=test_redis, token=access_token)

    access_payload = decode_token(access_token, expected_type="access")
    assert await test_redis.get(f"jwt_blocklist:{access_payload['jti']}") == "1"


@pytest.mark.parametrize("provider", ["google", "github"])
async def test_sso_flow_mocked_provider_responses(test_db, monkeypatch, provider: str):
    # Ensure provider appears configured.
    monkeypatch.setattr(auth_service.settings, "GOOGLE_CLIENT_ID", "x")
    monkeypatch.setattr(auth_service.settings, "GOOGLE_CLIENT_SECRET", "x")
    monkeypatch.setattr(auth_service.settings, "GITHUB_CLIENT_ID", "x")
    monkeypatch.setattr(auth_service.settings, "GITHUB_CLIENT_SECRET", "x")

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        async def authorize_access_token(self, request):
            _ = request
            if provider == "google":
                return {
                    "userinfo": {
                        "email": "sso-google@example.com",
                        "sub": "google-123",
                        "name": "Google User",
                        "picture": "https://example.com/google.png",
                    }
                }
            return {"access_token": "gh-token"}

        async def parse_id_token(self, request, token):
            _ = (request, token)
            return None

        async def get(self, path, token):
            _ = token
            if provider == "github" and path == "user":
                return FakeResponse({"id": 789, "login": "octocat", "name": "Octo Cat", "avatar_url": "https://example.com/gh.png"})
            if provider == "github" and path == "user/emails":
                return FakeResponse([{"email": "sso-github@example.com", "primary": True, "verified": True}])
            return FakeResponse({})

    monkeypatch.setattr(auth_service.oauth, "create_client", lambda _: FakeClient())

    result = await sso_callback_auth(request=SimpleNamespace(), db=test_db, provider=provider)
    assert result["access_token"]
    assert result["refresh_token"]
    if provider == "google":
        assert result["user"].email == "sso-google@example.com"
    else:
        assert result["user"].email == "sso-github@example.com"
