"""ItineraryPlaceService 유닛테스트.

repository는 AsyncMock으로 대체해서 DB 없이 서비스의 비즈니스 로직만 검증한다.
(일정/장소 없음 -> 404, 중복 담기/슬롯 충돌 -> 409, 정상 흐름)
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.services.itinerary_place_service import ItineraryPlaceService


@pytest.fixture
def mock_itinerary_place_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_itinerary_place_repo):
    return ItineraryPlaceService(mock_itinerary_place_repo)


# ------------------------------------------------------------------
# get_place_recommendations
# ------------------------------------------------------------------
class TestGetPlaceRecommendations:
    @pytest.mark.asyncio
    async def test_itinerary_not_found_raises_404(
        self, service, mock_itinerary_place_repo
    ):
        mock_itinerary_place_repo.get_itinerary.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.get_place_recommendations(uuid4())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_success_excludes_already_added_places(
        self, service, mock_itinerary_place_repo
    ):
        itinerary_id = uuid4()
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(region="제주")
        mock_itinerary_place_repo.get_existing_place_ids.return_value = {"place_1"}
        mock_itinerary_place_repo.get_recommended_places.return_value = [MagicMock()]

        result = await service.get_place_recommendations(itinerary_id, category="CAFE")

        assert result == mock_itinerary_place_repo.get_recommended_places.return_value
        mock_itinerary_place_repo.get_recommended_places.assert_called_once_with(
            region="제주",
            exclude_place_ids={"place_1"},
            category="CAFE",
        )


# ------------------------------------------------------------------
# add_place_to_itinerary
# ------------------------------------------------------------------
class TestAddPlaceToItinerary:
    @pytest.mark.asyncio
    async def test_itinerary_not_found_raises_404(
        self, service, mock_itinerary_place_repo
    ):
        mock_itinerary_place_repo.get_itinerary.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.add_place_to_itinerary(uuid4(), "place_1")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_place_not_found_raises_404(self, service, mock_itinerary_place_repo):
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock()
        mock_itinerary_place_repo.get_place.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.add_place_to_itinerary(uuid4(), "place_1")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicate_place_raises_409(self, service, mock_itinerary_place_repo):
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock()
        mock_itinerary_place_repo.get_place.return_value = MagicMock()
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = (
            MagicMock()
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.add_place_to_itinerary(uuid4(), "place_1")

        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_success_creates_itinerary_place_without_schedule(
        self, service, mock_itinerary_place_repo
    ):
        itinerary_id = uuid4()
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock()
        mock_itinerary_place_repo.get_place.return_value = MagicMock()
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = None
        mock_itinerary_place_repo.create_itinerary_place.return_value = MagicMock()

        result = await service.add_place_to_itinerary(itinerary_id, "place_1")

        assert result == mock_itinerary_place_repo.create_itinerary_place.return_value
        # 스케줄 미지정 시 슬롯 충돌 조회는 아예 호출되면 안 됨
        mock_itinerary_place_repo.get_itinerary_place_by_slot.assert_not_called()
        mock_itinerary_place_repo.create_itinerary_place.assert_called_once_with(
            itinerary_id,
            "place_1",
            day=None,
            time_slot=None,
            order_in_day=None,
        )

    @pytest.mark.asyncio
    async def test_success_creates_itinerary_place_with_schedule(
        self, service, mock_itinerary_place_repo
    ):
        itinerary_id = uuid4()
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock()
        mock_itinerary_place_repo.get_place.return_value = MagicMock()
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = None
        mock_itinerary_place_repo.get_itinerary_place_by_slot.return_value = None
        mock_itinerary_place_repo.create_itinerary_place.return_value = MagicMock()

        result = await service.add_place_to_itinerary(
            itinerary_id, "place_1", day=1, time_slot="MORNING", order_in_day=1
        )

        assert result == mock_itinerary_place_repo.create_itinerary_place.return_value
        mock_itinerary_place_repo.get_itinerary_place_by_slot.assert_called_once_with(
            itinerary_id, 1, "MORNING", 1
        )
        mock_itinerary_place_repo.create_itinerary_place.assert_called_once_with(
            itinerary_id,
            "place_1",
            day=1,
            time_slot="MORNING",
            order_in_day=1,
        )

    @pytest.mark.asyncio
    async def test_slot_conflict_raises_409(self, service, mock_itinerary_place_repo):
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock()
        mock_itinerary_place_repo.get_place.return_value = MagicMock()
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = None
        mock_itinerary_place_repo.get_itinerary_place_by_slot.return_value = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await service.add_place_to_itinerary(
                uuid4(), "place_1", day=1, time_slot="MORNING", order_in_day=1
            )

        assert exc_info.value.status_code == 409
        mock_itinerary_place_repo.create_itinerary_place.assert_not_called()

    @pytest.mark.asyncio
    async def test_integrity_error_fallback_raises_409(
        self, service, mock_itinerary_place_repo
    ):
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock()
        mock_itinerary_place_repo.get_place.return_value = MagicMock()
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = None
        mock_itinerary_place_repo.create_itinerary_place.side_effect = IntegrityError(
            "insert", {}, Exception("unique violation")
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.add_place_to_itinerary(uuid4(), "place_1")

        assert exc_info.value.status_code == 409


# ------------------------------------------------------------------
# remove_place_from_itinerary
# ------------------------------------------------------------------
class TestRemovePlaceFromItinerary:
    @pytest.mark.asyncio
    async def test_not_found_raises_404(self, service, mock_itinerary_place_repo):
        mock_itinerary_place_repo.get_itinerary_place.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.remove_place_from_itinerary(uuid4(), uuid4())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_belongs_to_other_itinerary_raises_404(
        self, service, mock_itinerary_place_repo
    ):
        other_itinerary_id = uuid4()
        mock_itinerary_place_repo.get_itinerary_place.return_value = MagicMock(
            itinerary_id=other_itinerary_id
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.remove_place_from_itinerary(uuid4(), uuid4())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_success_deletes_itinerary_place(
        self, service, mock_itinerary_place_repo
    ):
        itinerary_id = uuid4()
        mock_itinerary_place = MagicMock(itinerary_id=itinerary_id)
        mock_itinerary_place_repo.get_itinerary_place.return_value = (
            mock_itinerary_place
        )

        await service.remove_place_from_itinerary(itinerary_id, uuid4())

        mock_itinerary_place_repo.delete_itinerary_place.assert_called_once_with(
            mock_itinerary_place
        )
