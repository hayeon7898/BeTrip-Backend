import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.itinerary import Itinerary
from app.models.itinerary_place import ItineraryPlace
from app.models.place import Place


@pytest.fixture
def mock_itinerary_repo():
    return AsyncMock()


@pytest.fixture
def mock_kakao_map_client():
    return AsyncMock()


@pytest.fixture
def mock_kakao_mobility_client():
    return AsyncMock()


@pytest.fixture
def sample_user_id():
    return uuid.uuid4()


@pytest.fixture
def sample_itinerary(sample_user_id):
    return Itinerary(
        itinerary_id=uuid.uuid4(),
        user_id=sample_user_id,
        title="제주도 3박4일",
        status="DRAFT",
        region="제주도",
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 10),
        arrival_time="MORNING",
        departure_time="EVENING",
        transportation="CAR",
        purpose="FAMILY",
        styles=["NATURE", "FOOD"],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def make_itinerary_place(place_id: str, itinerary_id) -> ItineraryPlace:
    return ItineraryPlace(
        itinerary_place_id=uuid.uuid4(),
        itinerary_id=itinerary_id,
        place_id=place_id,
    )


def make_place(place_id: str, lat: float, lng: float) -> Place:
    return Place(
        place_id=place_id,
        name=f"장소-{place_id}",
        category="ACTIVITY",
        address="제주시 어딘가",
        lat=lat,
        lng=lng,
    )
