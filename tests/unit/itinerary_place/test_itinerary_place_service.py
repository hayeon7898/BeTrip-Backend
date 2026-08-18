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
def mock_kakao_map_client():
    return AsyncMock()


@pytest.fixture
def mock_kakao_mobility_client():
    return AsyncMock()


@pytest.fixture
def service(
    mock_itinerary_place_repo, mock_kakao_map_client, mock_kakao_mobility_client
):
    return ItineraryPlaceService(
        mock_itinerary_place_repo, mock_kakao_map_client, mock_kakao_mobility_client
    )


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
        created_place = MagicMock(time_slot="MORNING", travel_time_to_next_min=None)
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="CAR"
        )
        mock_itinerary_place_repo.get_place.return_value = MagicMock()
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = None
        mock_itinerary_place_repo.get_itinerary_place_by_slot.return_value = None
        mock_itinerary_place_repo.create_itinerary_place.return_value = created_place
        # 담긴 지 얼마 안 된 이 항목 혼자뿐인 day -> 앞/뒤 이웃 없음
        mock_itinerary_place_repo.find_day_places_ordered.return_value = [
            (created_place, MagicMock())
        ]

        result = await service.add_place_to_itinerary(
            itinerary_id, "place_1", day=1, time_slot="MORNING", order_in_day=1
        )

        assert result == created_place
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
        # 이웃이 없어 이동시간 갱신 대상은 없지만, 혼자뿐인 항목도 슬롯 기준
        # 시작시각(09:00)은 계산되어야 한다.
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [], [(created_place, "09:00")]
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
    async def test_success_deletes_unplaced_itinerary_place(
        self, service, mock_itinerary_place_repo
    ):
        """day가 None(미배치 상태)이면 인접 재계산 없이 단순 삭제한다."""
        itinerary_id = uuid4()
        mock_itinerary_place = MagicMock(itinerary_id=itinerary_id, day=None)
        mock_itinerary_place_repo.get_itinerary_place.return_value = (
            mock_itinerary_place
        )

        await service.remove_place_from_itinerary(itinerary_id, uuid4())

        mock_itinerary_place_repo.delete_itinerary_place.assert_called_once_with(
            mock_itinerary_place
        )
        mock_itinerary_place_repo.find_day_places_ordered.assert_not_awaited()
        mock_itinerary_place_repo.update_day_schedule.assert_not_awaited()


def make_ip(place_id: str, **overrides) -> MagicMock:
    defaults = {
        "itinerary_place_id": uuid4(),
        "place_id": place_id,
        "time_slot": "MORNING",
        "travel_time_to_next_min": None,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def make_place(lat: float, lng: float) -> MagicMock:
    return MagicMock(lat=lat, lng=lng)


# ------------------------------------------------------------------
# add_place_to_itinerary — 담기 직후 인접 구간 이동시간 원자적 반영
# ------------------------------------------------------------------
class TestAddPlaceTravelTimeRecalculation:
    @pytest.mark.asyncio
    async def test_no_schedule_skips_recalculation_entirely(
        self, service, mock_itinerary_place_repo
    ):
        """day/time_slot/order_in_day 없이 담으면 인접 재계산 자체가 안 붙는다."""
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock()
        mock_itinerary_place_repo.get_place.return_value = MagicMock()
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = None
        mock_itinerary_place_repo.create_itinerary_place.return_value = MagicMock()

        await service.add_place_to_itinerary(uuid4(), "place_1")

        mock_itinerary_place_repo.find_day_places_ordered.assert_not_awaited()
        mock_itinerary_place_repo.update_day_schedule.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_appended_last_updates_previous_items_travel_time(
        self, service, mock_itinerary_place_repo, mock_kakao_mobility_client
    ):
        """하루의 마지막 자리에 담으면: 이전 항목의 travel_time_to_next_min이 갱신되고,
        두 항목의 시작시각도 슬롯 기준으로 다시 계산된다."""
        itinerary_id = uuid4()
        prev_ip, prev_place = (
            make_ip("p1", time_slot="MORNING"),
            make_place(33.4, 126.5),
        )
        new_ip, new_place = make_ip("p2", time_slot="LUNCH"), make_place(33.41, 126.51)

        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="CAR"
        )
        mock_itinerary_place_repo.get_place.return_value = new_place
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = None
        mock_itinerary_place_repo.get_itinerary_place_by_slot.return_value = None
        mock_itinerary_place_repo.create_itinerary_place.return_value = new_ip
        mock_itinerary_place_repo.find_day_places_ordered.return_value = [
            (prev_ip, prev_place),
            (new_ip, new_place),
        ]
        mock_kakao_mobility_client.get_driving_route.return_value = {
            "duration_sec": 600
        }

        await service.add_place_to_itinerary(
            itinerary_id, "p2", day=1, time_slot="LUNCH", order_in_day=1
        )

        mock_kakao_mobility_client.get_driving_route.assert_awaited_once_with(
            prev_place.lng, prev_place.lat, new_place.lng, new_place.lat
        )
        # 09:00 출발 + 방문 90분 + 이동 10분 = 09:40, LUNCH 기준시각(12:00)이 더
        # 늦으므로 새 항목은 12:00으로 스냅된다.
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(prev_ip, 10)],
            [(prev_ip, "09:00"), (new_ip, "12:00")],
        )

    @pytest.mark.asyncio
    async def test_inserted_first_updates_own_travel_time_only(
        self, service, mock_itinerary_place_repo, mock_kakao_map_client
    ):
        """하루의 첫 자리에 담으면(=PUBLIC_TRANSPORT라 도보 모드): 새 항목 자신의
        travel_time_to_next_min이 갱신되고, 두 항목의 시작시각도 다시 계산된다."""
        itinerary_id = uuid4()
        new_ip, new_place = make_ip("p1", time_slot="MORNING"), make_place(33.4, 126.5)
        next_ip, next_place = (
            make_ip("p2", time_slot="LUNCH"),
            make_place(33.41, 126.51),
        )

        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="PUBLIC_TRANSPORT"
        )
        mock_itinerary_place_repo.get_place.return_value = new_place
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = None
        mock_itinerary_place_repo.get_itinerary_place_by_slot.return_value = None
        mock_itinerary_place_repo.create_itinerary_place.return_value = new_ip
        mock_itinerary_place_repo.find_day_places_ordered.return_value = [
            (new_ip, new_place),
            (next_ip, next_place),
        ]
        mock_kakao_map_client.get_walking_route.return_value = {"duration_sec": 300}

        await service.add_place_to_itinerary(
            itinerary_id, "p1", day=1, time_slot="MORNING", order_in_day=1
        )

        mock_kakao_map_client.get_walking_route.assert_awaited_once_with(
            new_place.lng, new_place.lat, next_place.lng, next_place.lat
        )
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(new_ip, 5)],
            [(new_ip, "09:00"), (next_ip, "12:00")],
        )

    @pytest.mark.asyncio
    async def test_inserted_middle_updates_both_neighbors(
        self, service, mock_itinerary_place_repo, mock_kakao_mobility_client
    ):
        itinerary_id = uuid4()
        prev_ip, prev_place = make_ip("p1", time_slot="LUNCH"), make_place(33.4, 126.5)
        new_ip, new_place = make_ip("p2", time_slot="LUNCH"), make_place(33.41, 126.51)
        next_ip, next_place = (
            make_ip("p3", time_slot="LUNCH"),
            make_place(33.42, 126.52),
        )

        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="CAR"
        )
        mock_itinerary_place_repo.get_place.return_value = new_place
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = None
        mock_itinerary_place_repo.get_itinerary_place_by_slot.return_value = None
        mock_itinerary_place_repo.create_itinerary_place.return_value = new_ip
        mock_itinerary_place_repo.find_day_places_ordered.return_value = [
            (prev_ip, prev_place),
            (new_ip, new_place),
            (next_ip, next_place),
        ]
        mock_kakao_mobility_client.get_driving_route.side_effect = [
            {"duration_sec": 300},  # prev -> new
            {"duration_sec": 480},  # new -> next
        ]

        await service.add_place_to_itinerary(
            itinerary_id, "p2", day=1, time_slot="LUNCH", order_in_day=2
        )

        assert mock_kakao_mobility_client.get_driving_route.await_count == 2
        # 12:00 + (방문 90분 + 이동 5분) = 13:35, + (방문 90분 + 이동 8분) = 15:13
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(prev_ip, 5), (new_ip, 8)],
            [(prev_ip, "12:00"), (new_ip, "13:35"), (next_ip, "15:13")],
        )

    @pytest.mark.asyncio
    async def test_kakao_failure_leaves_travel_time_none_but_add_succeeds(
        self, service, mock_itinerary_place_repo, mock_kakao_mobility_client
    ):
        itinerary_id = uuid4()
        prev_ip, prev_place = (
            make_ip("p1", time_slot="MORNING"),
            make_place(33.4, 126.5),
        )
        new_ip, new_place = make_ip("p2", time_slot="LUNCH"), make_place(33.41, 126.51)

        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="CAR"
        )
        mock_itinerary_place_repo.get_place.return_value = new_place
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = None
        mock_itinerary_place_repo.get_itinerary_place_by_slot.return_value = None
        mock_itinerary_place_repo.create_itinerary_place.return_value = new_ip
        mock_itinerary_place_repo.find_day_places_ordered.return_value = [
            (prev_ip, prev_place),
            (new_ip, new_place),
        ]
        mock_kakao_mobility_client.get_driving_route.side_effect = HTTPException(
            status_code=502, detail="카카오모빌리티 API 오류"
        )

        result = await service.add_place_to_itinerary(
            itinerary_id, "p2", day=1, time_slot="LUNCH", order_in_day=1
        )

        # 이동시간 계산이 실패해도 담기는 성공해야 하고, 실패 구간은 None으로 남지만
        # 시작시각은 이동시간을 0으로 취급해 그대로 계산된다.
        assert result is new_ip
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(prev_ip, None)],
            [(prev_ip, "09:00"), (new_ip, "12:00")],
        )


# ------------------------------------------------------------------
# remove_place_from_itinerary — 삭제 직후 인접 구간 이동시간 원자적 반영
# ------------------------------------------------------------------
class TestRemovePlaceTravelTimeRecalculation:
    @pytest.mark.asyncio
    async def test_removing_middle_item_reconnects_prev_to_next(
        self, service, mock_itinerary_place_repo, mock_kakao_mobility_client
    ):
        itinerary_id = uuid4()
        removed_id = uuid4()
        prev_ip, prev_place = (
            make_ip("p1", time_slot="MORNING"),
            make_place(33.4, 126.5),
        )
        removed_ip = make_ip("p2", itinerary_place_id=removed_id, day=1)
        next_ip, next_place = (
            make_ip("p3", time_slot="LUNCH"),
            make_place(33.42, 126.52),
        )

        mock_itinerary_place_repo.get_itinerary_place.return_value = MagicMock(
            itinerary_id=itinerary_id, itinerary_place_id=removed_id, day=1
        )
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="CAR"
        )
        mock_itinerary_place_repo.find_day_places_ordered.return_value = [
            (prev_ip, prev_place),
            (removed_ip, MagicMock()),
            (next_ip, next_place),
        ]
        mock_kakao_mobility_client.get_driving_route.return_value = {
            "duration_sec": 900
        }

        await service.remove_place_from_itinerary(itinerary_id, removed_id)

        mock_kakao_mobility_client.get_driving_route.assert_awaited_once_with(
            prev_place.lng, prev_place.lat, next_place.lng, next_place.lat
        )
        # 남은 두 항목(prev, next)만 기준으로 시작시각도 다시 계산된다.
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(prev_ip, 15)],
            [(prev_ip, "09:00"), (next_ip, "12:00")],
        )

    @pytest.mark.asyncio
    async def test_removing_last_item_clears_previous_travel_time(
        self, service, mock_itinerary_place_repo, mock_kakao_mobility_client
    ):
        itinerary_id = uuid4()
        removed_id = uuid4()
        prev_ip, prev_place = (
            make_ip("p1", time_slot="MORNING"),
            make_place(33.4, 126.5),
        )
        removed_ip = make_ip("p2", itinerary_place_id=removed_id, day=1)

        mock_itinerary_place_repo.get_itinerary_place.return_value = MagicMock(
            itinerary_id=itinerary_id, itinerary_place_id=removed_id, day=1
        )
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="CAR"
        )
        mock_itinerary_place_repo.find_day_places_ordered.return_value = [
            (prev_ip, prev_place),
            (removed_ip, MagicMock()),
        ]

        await service.remove_place_from_itinerary(itinerary_id, removed_id)

        mock_kakao_mobility_client.get_driving_route.assert_not_awaited()
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(prev_ip, None)],
            [(prev_ip, "09:00")],
        )

    @pytest.mark.asyncio
    async def test_removing_first_item_still_recalculates_remaining_start_times(
        self, service, mock_itinerary_place_repo, mock_kakao_mobility_client
    ):
        """앞 이웃이 없어 이동시간 갱신은 없지만, 남은 항목의 시작시각은
        하루 첫 자리로 당겨지므로 여전히 다시 계산되어야 한다."""
        itinerary_id = uuid4()
        removed_id = uuid4()
        removed_ip = make_ip("p1", itinerary_place_id=removed_id, day=1)
        next_ip, next_place = (
            make_ip("p2", time_slot="MORNING"),
            make_place(33.41, 126.51),
        )

        mock_itinerary_place_repo.get_itinerary_place.return_value = MagicMock(
            itinerary_id=itinerary_id, itinerary_place_id=removed_id, day=1
        )
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="CAR"
        )
        mock_itinerary_place_repo.find_day_places_ordered.return_value = [
            (removed_ip, MagicMock()),
            (next_ip, next_place),
        ]

        await service.remove_place_from_itinerary(itinerary_id, removed_id)

        mock_kakao_mobility_client.get_driving_route.assert_not_awaited()
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [], [(next_ip, "09:00")]
        )

    @pytest.mark.asyncio
    async def test_kakao_failure_leaves_travel_time_none_but_remove_succeeds(
        self, service, mock_itinerary_place_repo, mock_kakao_mobility_client
    ):
        itinerary_id = uuid4()
        removed_id = uuid4()
        prev_ip, prev_place = (
            make_ip("p1", time_slot="MORNING"),
            make_place(33.4, 126.5),
        )
        removed_ip = make_ip("p2", itinerary_place_id=removed_id, day=1)
        next_ip, next_place = (
            make_ip("p3", time_slot="LUNCH"),
            make_place(33.42, 126.52),
        )

        mock_itinerary_place_repo.get_itinerary_place.return_value = MagicMock(
            itinerary_id=itinerary_id, itinerary_place_id=removed_id, day=1
        )
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="CAR"
        )
        mock_itinerary_place_repo.find_day_places_ordered.return_value = [
            (prev_ip, prev_place),
            (removed_ip, MagicMock()),
            (next_ip, next_place),
        ]
        mock_kakao_mobility_client.get_driving_route.side_effect = HTTPException(
            status_code=503, detail="카카오모빌리티 API 오류"
        )

        await service.remove_place_from_itinerary(itinerary_id, removed_id)

        mock_itinerary_place_repo.delete_itinerary_place.assert_awaited_once()
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(prev_ip, None)],
            [(prev_ip, "09:00"), (next_ip, "12:00")],
        )
