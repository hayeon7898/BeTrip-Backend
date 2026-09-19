from datetime import timedelta


class TestSignupAPI:
    async def test_signup_success(self, client):
        response = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "new@example.com",
                "password": "Passw0rd!",
                "nickname": "새유저",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "new@example.com"
        assert "password_hash" not in data  # 민감정보 노출 안 되는지 확인

    async def test_signup_duplicate_email(self, client):
        payload = {
            "email": "dup@example.com",
            "password": "Passw0rd!",
            "nickname": "중복",
        }
        await client.post("/api/v1/auth/signup", json=payload)

        response = await client.post("/api/v1/auth/signup", json=payload)
        assert response.status_code == 409

    async def test_signup_weak_password_rejected(self, client):
        response = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "weak@example.com",
                "password": "weakpass",
                "nickname": "약함",
            },
        )
        assert response.status_code == 422  # 특수문자/대문자 없음


class TestLoginAPI:
    async def test_login_success_sets_refresh_cookie(self, client):
        signup_payload = {
            "email": "login@example.com",
            "password": "Passw0rd!",
            "nickname": "로그인",
        }
        await client.post("/api/v1/auth/signup", json=signup_payload)

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": "Passw0rd!"},
        )
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert "refresh_token" in response.cookies

    async def test_login_wrong_password(self, client):
        signup_payload = {
            "email": "wrongpw@example.com",
            "password": "Passw0rd!",
            "nickname": "테스트",
        }
        await client.post("/api/v1/auth/signup", json=signup_payload)

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrongpw@example.com", "password": "WrongOne!"},
        )
        assert response.status_code == 401


class TestRefreshAPI:
    async def test_refresh_flow_issues_new_token(self, client):
        signup_payload = {
            "email": "refresh@example.com",
            "password": "Passw0rd!",
            "nickname": "리프레시",
        }
        await client.post("/api/v1/auth/signup", json=signup_payload)

        login_response = await client.post(
            "/api/v1/auth/login",
            json={"email": "refresh@example.com", "password": "Passw0rd!"},
        )
        old_access_token = login_response.json()["access_token"]

        # client가 쿠키를 자동으로 들고 있으므로 별도 전달 불필요
        refresh_response = await client.post("/api/v1/auth/refresh")

        assert refresh_response.status_code == 200
        new_access_token = refresh_response.json()["access_token"]
        assert new_access_token != old_access_token

    async def test_refresh_without_cookie_fails(self, client):
        response = await client.post("/api/v1/auth/refresh")
        assert response.status_code == 401

    async def test_reuse_within_grace_returns_200(self, client):
        """로테이션 직후(유예 시간 내) 옛 토큰 재사용은 동시 요청으로 보고 통과"""
        await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "grace@example.com",
                "password": "Passw0rd!",
                "nickname": "유예",
            },
        )
        await client.post(
            "/api/v1/auth/login",
            json={"email": "grace@example.com", "password": "Passw0rd!"},
        )
        old_refresh_token = client.cookies.get("refresh_token")

        await client.post("/api/v1/auth/refresh")  # 로테이션
        new_refresh_token = client.cookies.get("refresh_token")

        client.cookies.clear()
        client.cookies.set("refresh_token", old_refresh_token)
        response = await client.post("/api/v1/auth/refresh")
        assert response.status_code == 200

        # 전체 세션이 폐기되지 않았으므로 새 토큰도 여전히 유효해야 함
        client.cookies.clear()
        client.cookies.set("refresh_token", new_refresh_token)
        response = await client.post("/api/v1/auth/refresh")
        assert response.status_code == 200

    async def test_reused_refresh_token_after_grace_revokes_session(
        self, client, monkeypatch
    ):
        """유예 시간 이후 옛 토큰 재사용은 탈취로 보고 401 + 전체 세션 폐기"""
        monkeypatch.setattr(
            "app.services.auth_service.REUSE_GRACE", timedelta(seconds=-1)
        )  # 항상 유예 밖으로 취급

        await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "reuse@example.com",
                "password": "Passw0rd!",
                "nickname": "재사용",
            },
        )
        await client.post(
            "/api/v1/auth/login",
            json={"email": "reuse@example.com", "password": "Passw0rd!"},
        )
        old_refresh_token = client.cookies.get("refresh_token")

        await client.post("/api/v1/auth/refresh")  # 로테이션
        new_refresh_token = client.cookies.get("refresh_token")

        client.cookies.clear()
        client.cookies.set("refresh_token", old_refresh_token)
        response = await client.post("/api/v1/auth/refresh")
        assert response.status_code == 401

        # 탈취 감지로 새 토큰까지 전부 폐기됐는지 확인
        client.cookies.clear()
        client.cookies.set("refresh_token", new_refresh_token)
        response = await client.post("/api/v1/auth/refresh")
        assert response.status_code == 401


class TestLogoutAPI:
    async def test_logout_revokes_refresh_token(self, client, monkeypatch):
        # 방금 폐기된 토큰은 유예 시간 안이라 200이 나오므로, 유예 밖으로 취급해 검증
        monkeypatch.setattr(
            "app.services.auth_service.REUSE_GRACE", timedelta(seconds=-1)
        )
        await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "logout@example.com",
                "password": "Passw0rd!",
                "nickname": "로그아웃",
            },
        )
        await client.post(
            "/api/v1/auth/login",
            json={"email": "logout@example.com", "password": "Passw0rd!"},
        )
        refresh_token = client.cookies.get("refresh_token")

        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 204

        # 로그아웃된 토큰으로는 refresh 불가
        client.cookies.clear()
        client.cookies.set("refresh_token", refresh_token)
        response = await client.post("/api/v1/auth/refresh")
        assert response.status_code == 401
