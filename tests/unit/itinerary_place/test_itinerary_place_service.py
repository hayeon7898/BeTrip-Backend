"""ItineraryPlaceService 유닛테스트.

repository는 AsyncMock으로 대체해서 DB 없이 서비스의 비즈니스 로직만 검증한다.
(일정/장소 없음 -> 404, 중복 담기/슬롯 충돌 -> 409, 정상 흐름)

NOTE: _recalculate_day는 담기/삭제/이동/재정렬 전부에서 공용으로 쓰이며,
day 전체를 훑어 인접 구간 이동시간을 갱신하고, 마지막 아이템은 항상
travel_time_to_next_min=None으로 명시 세팅한다. 따라서 update_day_schedule의
travel_updates에는 "마지막 아이템, None" 튜플이 항상 마지막에 붙는다.
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
        # 스케줄 미지정 시 슬롯 충돌 조회 및 day 재계산 자체가 호출되면 안 됨
        mock_itinerary_place_repo.get_itinerary_place_by_slot.assert_not_called()
        mock_itinerary_place_repo.find_day_places_ordered.assert_not_awaited()
        mock_itinerary_place_repo.create_itinerary_place.assert_called_once_with(
            itinerary_id,
            "place_1",
            day=None,
            time_slot=None,
            order_in_day=None,
        )
        mock_itinerary_place_repo.commit.assert_awaited_once()

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
        # 담긴 지 얼마 안 된 이 항목 혼자뿐인 day -> 이웃 없음, 자기 자신이 마지막
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
        # 이웃은 없지만, 혼자뿐인 항목도 "마지막"이라 (created_place, None)이 붙고
        # 슬롯 기준 시작시각(09:00)도 계산된다.
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(created_place, None)], [(created_place, "09:00")]
        )
        mock_itinerary_place_repo.commit.assert_awaited_once()
        mock_itinerary_place_repo.refresh_itinerary_place.assert_awaited_once_with(
            created_place
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
        """day가 None(미배치 상태)이면 재계산 없이 단순 삭제한다."""
        itinerary_id = uuid4()
        mock_itinerary_place = MagicMock(itinerary_id=itinerary_id, day=None)
        mock_itinerary_place_repo.get_itinerary_place.return_value = (
            mock_itinerary_place
        )

        await service.remove_place_from_itinerary(itinerary_id, uuid4())

        mock_itinerary_place_repo.delete_itinerary_place.assert_awaited_once_with(
            mock_itinerary_place
        )
        mock_itinerary_place_repo.find_day_places_ordered.assert_not_awaited()
        mock_itinerary_place_repo.update_day_schedule.assert_not_awaited()
        mock_itinerary_place_repo.commit.assert_awaited_once()


# ------------------------------------------------------------------
# add_place_to_itinerary — 담기 직후 day 전체 재계산
# ------------------------------------------------------------------
class TestAddPlaceTravelTimeRecalculation:
    @pytest.mark.asyncio
    async def test_no_schedule_skips_recalculation_entirely(
        self, service, mock_itinerary_place_repo
    ):
        """day/time_slot/order_in_day 없이 담으면 재계산 자체가 안 붙는다."""
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
        새 항목(마지막)은 명시적으로 None, 두 항목의 시작시각도 다시 계산된다."""
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
        # prev->new 구간(10분) + 마지막 항목(new_ip)은 명시적으로 None
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(prev_ip, 10), (new_ip, None)],
            [(prev_ip, "09:00"), (new_ip, "12:00")],
        )

    @pytest.mark.asyncio
    async def test_inserted_first_updates_own_travel_time_only(
        self, service, mock_itinerary_place_repo, mock_kakao_map_client
    ):
        """하루의 첫 자리에 담으면(=PUBLIC_TRANSPORT라 도보 모드): 새 항목 자신의
        travel_time_to_next_min이 갱신되고, 마지막 항목은 명시적으로 None."""
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
            [(new_ip, 5), (next_ip, None)],
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
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(prev_ip, 5), (new_ip, 8), (next_ip, None)],
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

        assert result is new_ip
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(prev_ip, None), (new_ip, None)],
            [(prev_ip, "09:00"), (new_ip, "12:00")],
        )


# ------------------------------------------------------------------
# remove_place_from_itinerary — 삭제 직후 day 전체 재계산
#
# NOTE: 삭제(delete_itinerary_place)가 먼저 일어난 뒤 find_day_places_ordered를
# 호출하는 구조이므로, mock의 return_value는 "삭제된 아이템이 이미 빠진"
# 남은 상태를 반환해야 한다 (실제 DB라면 당연히 그렇게 동작함).
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
        # 삭제 이후 남은 상태만 반환 (removed_ip는 이미 빠짐)
        mock_itinerary_place_repo.find_day_places_ordered.return_value = [
            (prev_ip, prev_place),
            (next_ip, next_place),
        ]
        mock_kakao_mobility_client.get_driving_route.return_value = {
            "duration_sec": 900
        }

        await service.remove_place_from_itinerary(itinerary_id, removed_id)

        mock_kakao_mobility_client.get_driving_route.assert_awaited_once_with(
            prev_place.lng, prev_place.lat, next_place.lng, next_place.lat
        )
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(prev_ip, 15), (next_ip, None)],
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

        mock_itinerary_place_repo.get_itinerary_place.return_value = MagicMock(
            itinerary_id=itinerary_id, itinerary_place_id=removed_id, day=1
        )
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="CAR"
        )
        # 삭제된 항목이 마지막이었으므로 남는 건 prev_ip 하나
        mock_itinerary_place_repo.find_day_places_ordered.return_value = [
            (prev_ip, prev_place),
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
        # 삭제된 항목이 첫 자리였으므로 남는 건 next_ip 하나
        mock_itinerary_place_repo.find_day_places_ordered.return_value = [
            (next_ip, next_place),
        ]

        await service.remove_place_from_itinerary(itinerary_id, removed_id)

        mock_kakao_mobility_client.get_driving_route.assert_not_awaited()
        # 남은 항목 1개도 "마지막"이라 (next_ip, None)이 명시적으로 붙는다
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(next_ip, None)], [(next_ip, "09:00")]
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
            (next_ip, next_place),
        ]
        mock_kakao_mobility_client.get_driving_route.side_effect = HTTPException(
            status_code=503, detail="카카오모빌리티 API 오류"
        )

        await service.remove_place_from_itinerary(itinerary_id, removed_id)

        mock_itinerary_place_repo.delete_itinerary_place.assert_awaited_once()
        mock_itinerary_place_repo.update_day_schedule.assert_awaited_once_with(
            [(prev_ip, None), (next_ip, None)],
            [(prev_ip, "09:00"), (next_ip, "12:00")],
        )


# ------------------------------------------------------------------
# move_place — 슬롯/일차 이동 PATCH /{place_id}
# ------------------------------------------------------------------
class TestMovePlace:
    @pytest.mark.asyncio
    async def test_itinerary_not_found_raises_404(
        self, service, mock_itinerary_place_repo
    ):
        mock_itinerary_place_repo.get_itinerary.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.move_place(uuid4(), "p1", day=2, time_slot="LUNCH")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_itinerary_place_not_found_raises_404(
        self, service, mock_itinerary_place_repo
    ):
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock()
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.move_place(uuid4(), "p1", day=2, time_slot="LUNCH")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_move_within_same_day_recalculates_once(
        self, service, mock_itinerary_place_repo
    ):
        """같은 day 안에서 슬롯만 바꾸면 old_day == new day라 재계산은 1번만."""
        itinerary_id = uuid4()
        itinerary_place = make_ip("p1", day=2, time_slot="MORNING", order_in_day=1)

        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="CAR", itinerary_id=itinerary_id
        )
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = (
            itinerary_place
        )
        mock_itinerary_place_repo.get_max_order_in_slot.return_value = 2
        mock_itinerary_place_repo.find_day_places_ordered.return_value = []

        await service.move_place(itinerary_id, "p1", day=2, time_slot="LUNCH")

        mock_itinerary_place_repo.get_max_order_in_slot.assert_awaited_once_with(
            itinerary_id, 2, "LUNCH"
        )
        # 슬롯 맨 뒤(max+1)로 배치, day/time_slot 갱신 확인
        assert itinerary_place.day == 2
        assert itinerary_place.time_slot == "LUNCH"
        assert itinerary_place.order_in_day == 3
        mock_itinerary_place_repo.flush.assert_awaited_once()
        # old_day == new day(2) 이므로 find_day_places_ordered는 day=2로 1번만
        mock_itinerary_place_repo.find_day_places_ordered.assert_awaited_once_with(
            itinerary_id, 2
        )
        mock_itinerary_place_repo.commit.assert_awaited_once()
        mock_itinerary_place_repo.refresh_itinerary_place.assert_awaited_once_with(
            itinerary_place
        )

    @pytest.mark.asyncio
    async def test_move_to_different_day_recalculates_both_days(
        self, service, mock_itinerary_place_repo
    ):
        """다른 day로 이동하면 원래 day와 이동한 day 둘 다 재계산된다."""
        itinerary_id = uuid4()
        itinerary_place = make_ip("p1", day=1, time_slot="MORNING", order_in_day=1)

        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="CAR", itinerary_id=itinerary_id
        )
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = (
            itinerary_place
        )
        mock_itinerary_place_repo.get_max_order_in_slot.return_value = 0
        mock_itinerary_place_repo.find_day_places_ordered.return_value = []

        await service.move_place(itinerary_id, "p1", day=3, time_slot="EVENING")

        assert itinerary_place.day == 3
        assert itinerary_place.time_slot == "EVENING"
        assert itinerary_place.order_in_day == 1

        await_args_list = (
            mock_itinerary_place_repo.find_day_places_ordered.await_args_list
        )
        called_days = {call.args[1] for call in await_args_list}
        assert called_days == {1, 3}
        assert mock_itinerary_place_repo.find_day_places_ordered.await_count == 2
        mock_itinerary_place_repo.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_move_from_unplaced_state_only_recalculates_target_day(
        self, service, mock_itinerary_place_repo
    ):
        """old_day가 None(미배치)이었으면 재계산 대상은 이동한 day 하나뿐."""
        itinerary_id = uuid4()
        itinerary_place = make_ip("p1", day=None, time_slot=None, order_in_day=None)

        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="CAR", itinerary_id=itinerary_id
        )
        mock_itinerary_place_repo.get_itinerary_place_by_place_id.return_value = (
            itinerary_place
        )
        mock_itinerary_place_repo.get_max_order_in_slot.return_value = 0
        mock_itinerary_place_repo.find_day_places_ordered.return_value = []

        await service.move_place(itinerary_id, "p1", day=1, time_slot="MORNING")

        mock_itinerary_place_repo.find_day_places_ordered.assert_awaited_once_with(
            itinerary_id, 1
        )


# ------------------------------------------------------------------
# reorder_places — 같은 슬롯 내 순서 재정렬 PATCH /reorder
# ------------------------------------------------------------------
class TestReorderPlaces:
    @pytest.mark.asyncio
    async def test_itinerary_not_found_raises_404(
        self, service, mock_itinerary_place_repo
    ):
        mock_itinerary_place_repo.get_itinerary.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.reorder_places(
                uuid4(), day=1, time_slot="LUNCH", place_ids=["p1", "p2"]
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_place_ids_count_mismatch_raises_400(
        self, service, mock_itinerary_place_repo
    ):
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock()
        mock_itinerary_place_repo.find_slot_places.return_value = [
            make_ip("p1"),
            make_ip("p2"),
        ]

        with pytest.raises(HTTPException) as exc_info:
            await service.reorder_places(
                uuid4(), day=1, time_slot="LUNCH", place_ids=["p1", "p2", "p3"]
            )

        assert exc_info.value.status_code == 400
        mock_itinerary_place_repo.update_day_schedule.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_place_ids_content_mismatch_raises_400(
        self, service, mock_itinerary_place_repo
    ):
        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock()
        mock_itinerary_place_repo.find_slot_places.return_value = [
            make_ip("p1"),
            make_ip("p2"),
        ]

        with pytest.raises(HTTPException) as exc_info:
            await service.reorder_places(
                uuid4(), day=1, time_slot="LUNCH", place_ids=["p1", "p3"]
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_success_reassigns_order_and_recalculates_day(
        self, service, mock_itinerary_place_repo
    ):
        itinerary_id = uuid4()
        ip1 = make_ip("p1", day=1, time_slot="LUNCH", order_in_day=1)
        ip2 = make_ip("p2", day=1, time_slot="LUNCH", order_in_day=2)
        ip3 = make_ip("p3", day=1, time_slot="LUNCH", order_in_day=3)

        mock_itinerary_place_repo.get_itinerary.return_value = MagicMock(
            transportation="CAR", itinerary_id=itinerary_id
        )
        mock_itinerary_place_repo.find_slot_places.return_value = [ip1, ip2, ip3]
        mock_itinerary_place_repo.find_day_places_ordered.return_value = []

        result = await service.reorder_places(
            itinerary_id, day=1, time_slot="LUNCH", place_ids=["p3", "p1", "p2"]
        )

        # 요청한 순서(p3, p1, p2)대로 order_in_day가 1부터 재부여됨
        assert ip3.order_in_day == 1
        assert ip1.order_in_day == 2
        assert ip2.order_in_day == 3
        mock_itinerary_place_repo.flush.assert_awaited_once()
        mock_itinerary_place_repo.find_day_places_ordered.assert_awaited_once_with(
            itinerary_id, 1
        )
        mock_itinerary_place_repo.commit.assert_awaited_once()
        # 응답도 place_ids 순서(p3, p1, p2) 그대로
        assert result == [ip3, ip1, ip2]
