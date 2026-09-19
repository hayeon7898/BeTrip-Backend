from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.core.config import settings
from app.core.deps import get_auth_service
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = f"{settings.API_V1_PREFIX}/auth"


def _set_refresh_cookie(response: Response, raw_token: str):
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,  # 로컬 http는 False
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
    )


@router.post(
    "/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def signup(req: SignupRequest, service: AuthService = Depends(get_auth_service)):
    return await service.signup(req)


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    access_token, raw_refresh_token, _user = await service.login(req)
    _set_refresh_cookie(response, raw_refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    service: AuthService = Depends(get_auth_service),
):
    if refresh_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "리프레시 토큰이 없습니다.")

    access, new_raw = await service.refresh(refresh_token)
    if new_raw:  # 새 토큰이 있을 때만 쿠키 갱신 (grace 구간에서는 None)
        _set_refresh_cookie(response, new_raw)
    return TokenResponse(access_token=access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    service: AuthService = Depends(get_auth_service),
):
    if refresh_token:
        await service.logout(refresh_token)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
