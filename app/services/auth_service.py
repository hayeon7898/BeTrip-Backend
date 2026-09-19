from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, SignupRequest

REUSE_GRACE = timedelta(seconds=30)


class AuthService:
    def __init__(self, user_repo: UserRepository, token_repo: RefreshTokenRepository):
        self.user_repo = user_repo
        self.token_repo = token_repo

    async def signup(self, req: SignupRequest) -> User:
        if await self.user_repo.exists_by_email(req.email):
            raise HTTPException(status.HTTP_409_CONFLICT, "이미 가입된 이메일입니다.")

        hashed_pw = await run_in_threadpool(hash_password, req.password)

        user = User(
            email=req.email,
            password_hash=hashed_pw,
            nickname=req.nickname,
            provider="LOCAL",
        )
        return await self.user_repo.save(user)

    async def login(self, req: LoginRequest) -> tuple[str, str, User]:
        user = await self.user_repo.find_by_email(req.email)
        if not user:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "이메일 또는 비밀번호가 올바르지 않습니다.",
            )

        is_valid = await run_in_threadpool(
            verify_password, req.password, user.password_hash
        )
        if not is_valid:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "이메일 또는 비밀번호가 올바르지 않습니다.",
            )

        access_token = create_access_token(str(user.user_id))
        raw_refresh_token = await self._issue_refresh_token(user.user_id)

        return access_token, raw_refresh_token, user

    async def refresh(self, raw_refresh_token: str) -> tuple[str, str | None]:
        token_hash = hash_refresh_token(raw_refresh_token)

        row = await self.token_repo.revoke_if_active(token_hash)
        if row:
            access = create_access_token(str(row.user_id))
            new_raw = await self._issue_refresh_token(row.user_id)
            return access, new_raw

        old = await self.token_repo.find_by_hash_including_revoked(token_hash)
        if old and old.revoked_at is not None:
            if datetime.now(timezone.utc) - old.revoked_at <= REUSE_GRACE:
                return create_access_token(
                    str(old.user_id)
                ), None  # 동시 요청: access만 재발급
            await self.token_repo.revoke_all_for_user(
                old.user_id
            )  # 유예 이후 재사용만 탈취로 간주

        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "리프레시 토큰이 유효하지 않습니다. 다시 로그인해주세요.",
        )

    async def logout(self, raw_refresh_token: str) -> None:
        await self.token_repo.revoke_if_active(hash_refresh_token(raw_refresh_token))

    async def _issue_refresh_token(self, user_id) -> str:
        raw_token = generate_refresh_token()
        token_row = RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            created_at=datetime.now(timezone.utc),
        )
        await self.token_repo.save(token_row)
        return raw_token
