"""itinerary_place 통합테스트 전용 데이터 픽스처.

db_session은 상위 tests/integration/conftest.py의 픽스처를 그대로 상속받아
쓴다 (여기서 새로 정의하지 않음 - engine을 fixture마다 새로 만드는 이유는
pytest-asyncio가 테스트마다 다른 이벤트 루프를 쓸 수 있어서, 엔진을
모듈 레벨에서 재사용하면 이벤트 루프 불일치 에러가 나기 때문).
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.models.itinerary import Itinerary
from app.models.place import Place
from app.models.user import User


@pytest.fixture
async def signed_up_user(client):
    """회원가입 + 로그인 후 (access_token, user_id)를 반환한다."""
    payload = {
        "email": f"{uuid4()}@example.com",
        "password": "Passw0rd!",
        "nickname": "테스터",
    }
    signup_res = await client.post("/api/v1/auth/signup", json=payload)
    user_id = UUID(signup_res.json()["user_id"])

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    access_token = login_res.json()["access_token"]
    return access_token, user_id


@pytest_asyncio.fixture
async def sample_user(db_session):
    from app.core.security import hash_password

    user = User(
        email=f"test-{uuid4()}@example.com",
        password_hash=hash_password("Passw0rd!"),
        nickname="테스터",
        provider="LOCAL",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def sample_itinerary(db_session, sample_user):
    itinerary = Itinerary(
        user_id=sample_user.user_id,
        title="제주 여행",
        region="제주",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 3),
        arrival_time="MORNING",
        departure_time="EVENING",
        transportation="CAR",
        purpose="FRIEND",
        styles=[],
    )
    db_session.add(itinerary)
    await db_session.commit()
    await db_session.refresh(itinerary)
    return itinerary


@pytest_asyncio.fixture
async def sample_place():
    def _make(**overrides):
        defaults = dict(
            place_id=f"kakao-{uuid4()}",
            name="테스트 카페",
            category="CAFE",
            address="제주특별자치도 제주시 테스트로 1",
            lat=33.4,
            lng=126.5,
        )
        defaults.update(overrides)
        return Place(**defaults)

    return _make
