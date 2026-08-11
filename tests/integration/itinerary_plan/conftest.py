import uuid

import pytest


@pytest.fixture
async def signed_up_user(client):
    """회원가입 + 로그인 후 (access_token, user_id)를 반환한다."""
    payload = {
        "email": f"{uuid.uuid4()}@example.com",
        "password": "Passw0rd!",
        "nickname": "테스터",
    }
    signup_res = await client.post("/api/v1/auth/signup", json=payload)
    user_id = uuid.UUID(signup_res.json()["user_id"])

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    access_token = login_res.json()["access_token"]
    return access_token, user_id
