from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import User, get_db_session
from app.models.schemas import (
    AuthLoginRequest,
    AuthMeResponse,
    AuthRefreshResponse,
    AuthRequestOtpRequest,
    AuthRegisterRequest,
    AuthSsoCallbackResponse,
    AuthTokenUserResponse,
    AuthUpdateMeRequest,
    AuthVerifyOtpRequest,
    MessageResponse,
)
from app.services.auth_service import (
    AuthService,
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    get_current_user,
    get_redis,
    get_sso_redirect,
    oauth2_scheme,
    set_refresh_cookie,
    sso_callback_auth,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=MessageResponse)
async def register(
    payload: AuthRegisterRequest,
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> MessageResponse:
    result = await AuthService.register(
        db=db,
        redis=redis,
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
    )
    return MessageResponse(**result)


@router.post("/verify-otp", response_model=AuthTokenUserResponse)
async def verify_otp(
    payload: AuthVerifyOtpRequest,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> AuthTokenUserResponse:
    result = await AuthService.verify_otp(
        db=db,
        email=payload.email,
        code=payload.code,
        purpose=payload.purpose.value,
    )
    set_refresh_cookie(response, result["refresh_token"])
    return AuthTokenUserResponse(access_token=result["access_token"], user=result["user"])


@router.post("/login", response_model=AuthTokenUserResponse)
async def login(
    payload: AuthLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> AuthTokenUserResponse:
    result = await AuthService.login_with_password(db=db, email=payload.email, password=payload.password)
    set_refresh_cookie(response, result["refresh_token"])
    return AuthTokenUserResponse(access_token=result["access_token"], user=result["user"])


@router.post("/request-otp", response_model=MessageResponse)
async def request_otp(
    payload: AuthRequestOtpRequest,
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> MessageResponse:
    result = await AuthService.request_login_otp(db=db, redis=redis, email=payload.email)
    return MessageResponse(**result)


@router.post("/refresh", response_model=AuthRefreshResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> AuthRefreshResponse:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")

    result = await AuthService.refresh(db=db, redis=redis, refresh_token=refresh_token)
    set_refresh_cookie(response, result["refresh_token"])
    return AuthRefreshResponse(access_token=result["access_token"])


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    token: str = Depends(oauth2_scheme),
    redis: Redis = Depends(get_redis),
) -> MessageResponse:
    await AuthService.logout(redis=redis, token=token)
    clear_refresh_cookie(response)
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=AuthMeResponse)
async def me(current_user: User = Depends(get_current_user)) -> AuthMeResponse:
    return AuthMeResponse.model_validate(current_user)


@router.patch("/me", response_model=AuthMeResponse)
async def update_me(
    payload: AuthUpdateMeRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> AuthMeResponse:
    updated_user = await AuthService.update_me(
        db=db,
        user=current_user,
        full_name=payload.full_name,
        avatar_url=payload.avatar_url,
    )
    return AuthMeResponse.model_validate(updated_user)


@router.get("/sso/{provider}")
async def sso_start(provider: str, request: Request):
    return await get_sso_redirect(request=request, provider=provider)


@router.get("/sso/{provider}/callback", response_model=AuthSsoCallbackResponse)
async def sso_callback(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    result = await sso_callback_auth(request=request, db=db, provider=provider)

    payload = AuthSsoCallbackResponse(access_token=result["access_token"], user=result["user"]).model_dump()
    response = JSONResponse(content=payload)
    set_refresh_cookie(response, result["refresh_token"])
    return response
