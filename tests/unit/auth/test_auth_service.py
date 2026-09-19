from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core.security import hash_refresh_token
from app.schemas.auth import LoginRequest, SignupRequest
from app.services.auth_service import AuthService


class TestSignup:
    async def test_signup_success(self, mock_user_repo, mock_token_repo):
        mock_user_repo.exists_by_email.return_value = False
        mock_user_repo.save.side_effect = lambda user: user  # 저장된 user 그대로 반환

        service = AuthService(mock_user_repo, mock_token_repo)
        req = SignupRequest(
            email="new@example.com", password="Passw0rd!", nickname="새유저"
        )

        result = await service.signup(req)

        assert result.email == "new@example.com"
        assert result.password_hash != "Passw0rd!"  # 평문 저장 안 됐는지 확인
        mock_user_repo.save.assert_awaited_once()

    async def test_signup_duplicate_email(self, mock_user_repo, mock_token_repo):
        mock_user_repo.exists_by_email.return_value = True

        service = AuthService(mock_user_repo, mock_token_repo)
        req = SignupRequest(
            email="dup@example.com", password="Passw0rd!", nickname="중복"
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.signup(req)

        assert exc_info.value.status_code == 409
        mock_user_repo.save.assert_not_awaited()


class TestLogin:
    async def test_login_success(self, mock_user_repo, mock_token_repo, sample_user):
        mock_user_repo.find_by_email.return_value = sample_user
        mock_token_repo.save.side_effect = lambda token: token

        service = AuthService(mock_user_repo, mock_token_repo)
        req = LoginRequest(email=sample_user.email, password="Passw0rd!")

        access_token, raw_refresh_token, user = await service.login(req)

        assert access_token is not None
        assert raw_refresh_token is not None
        assert user.email == sample_user.email
        mock_token_repo.save.assert_awaited_once()

    async def test_login_wrong_password(
        self, mock_user_repo, mock_token_repo, sample_user
    ):
        mock_user_repo.find_by_email.return_value = sample_user

        service = AuthService(mock_user_repo, mock_token_repo)
        req = LoginRequest(email=sample_user.email, password="WrongPassword!")

        with pytest.raises(HTTPException) as exc_info:
            await service.login(req)

        assert exc_info.value.status_code == 401

    async def test_login_user_not_found(self, mock_user_repo, mock_token_repo):
        mock_user_repo.find_by_email.return_value = None

        service = AuthService(mock_user_repo, mock_token_repo)
        req = LoginRequest(email="nobody@example.com", password="whatever")

        with pytest.raises(HTTPException) as exc_info:
            await service.login(req)

        assert exc_info.value.status_code == 401


class TestRefresh:
    async def test_refresh_success_rotates_token(
        self, mock_user_repo, mock_token_repo, sample_refresh_token
    ):
        raw_token, token_row = sample_refresh_token
        mock_token_repo.revoke_if_active.return_value = token_row
        mock_token_repo.save.side_effect = lambda t: t

        service = AuthService(mock_user_repo, mock_token_repo)
        new_access_token, new_raw_refresh_token = await service.refresh(raw_token)

        assert new_access_token is not None
        assert new_raw_refresh_token is not None
        assert new_raw_refresh_token != raw_token  # 새 토큰 발급 확인
        mock_token_repo.revoke_if_active.assert_awaited_once_with(
            hash_refresh_token(raw_token)
        )  # 기존 토큰 폐기 확인
        mock_token_repo.save.assert_awaited_once()

    async def test_refresh_with_invalid_token_raises_401(
        self, mock_user_repo, mock_token_repo
    ):
        mock_token_repo.revoke_if_active.return_value = None
        mock_token_repo.find_by_hash_including_revoked.return_value = None

        service = AuthService(mock_user_repo, mock_token_repo)

        with pytest.raises(HTTPException) as exc_info:
            await service.refresh("invalid-token")

        assert exc_info.value.status_code == 401
        mock_token_repo.revoke_all_for_user.assert_not_awaited()

    async def test_refresh_reuse_within_grace_returns_access_only(
        self, mock_user_repo, mock_token_repo, sample_refresh_token
    ):
        """동시 요청 시나리오: 방금 폐기된 토큰이면 탈취로 보지 않고
        access token만 재발급하며, 전체 세션은 폐기하지 않아야 함"""
        raw_token, token_row = sample_refresh_token
        token_row.revoked_at = datetime.now(timezone.utc) - timedelta(seconds=5)

        mock_token_repo.revoke_if_active.return_value = None
        mock_token_repo.find_by_hash_including_revoked.return_value = token_row

        service = AuthService(mock_user_repo, mock_token_repo)
        access, new_raw = await service.refresh(raw_token)

        assert access is not None
        assert new_raw is None  # 새 refresh 쿠키는 발급하지 않음
        mock_token_repo.revoke_all_for_user.assert_not_awaited()
        mock_token_repo.save.assert_not_awaited()

    async def test_refresh_with_reused_revoked_token_revokes_all_sessions(
        self, mock_user_repo, mock_token_repo, sample_refresh_token
    ):
        """유예 시간 이후 폐기된 토큰을 재사용하면 탈취로 보고
        해당 유저의 모든 refresh token을 무효화해야 함"""
        raw_token, token_row = sample_refresh_token
        token_row.revoked_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        mock_token_repo.revoke_if_active.return_value = None
        mock_token_repo.find_by_hash_including_revoked.return_value = token_row

        service = AuthService(mock_user_repo, mock_token_repo)

        with pytest.raises(HTTPException) as exc_info:
            await service.refresh(raw_token)

        assert exc_info.value.status_code == 401
        mock_token_repo.revoke_all_for_user.assert_awaited_once_with(token_row.user_id)


class TestLogout:
    async def test_logout_revokes_token(self, mock_user_repo, mock_token_repo):
        service = AuthService(mock_user_repo, mock_token_repo)

        await service.logout("some-raw-token")

        mock_token_repo.revoke_if_active.assert_awaited_once_with(
            hash_refresh_token("some-raw-token")
        )
