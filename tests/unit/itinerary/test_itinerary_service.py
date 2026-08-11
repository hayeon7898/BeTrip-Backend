import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException

from app.schemas.itinerary import ItineraryConditionsRequest
from app.services.itinerary_service import ItineraryService


def _fake_saved(itinerary):
    """실제 repo.create()가 DB insert 후 채워주는 필드(PK/생성시각)를 흉내낸다."""
    itinerary.itinerary_id = uuid.uuid4()
    itinerary.created_at = datetime.now(timezone.utc)
    return itinerary


class TestCreateItinerary:
    async def test_create_success_maps_request_and_returns_draft(
        self, mock_itinerary_repo, sample_user_id
    ):
        mock_itinerary_repo.create.side_effect = _fake_saved

        service = ItineraryService(mock_itinerary_repo)
        req = ItineraryConditionsRequest(
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 13),
            region="제주도",
            arrival_time="LUNCH",
            departure_time="MORNING",
            transportation="CAR",
            purpose="FAMILY",
            styles=["NATURE", "FOOD"],
        )

        result = await service.create_itinerary(sample_user_id, req)

        assert result.status == "DRAFT"
        mock_itinerary_repo.create.assert_awaited_once()
        created_itinerary = mock_itinerary_repo.create.await_args.args[0]
        assert created_itinerary.user_id == sample_user_id
        assert created_itinerary.region == "제주도"
        assert created_itinerary.transportation == "CAR"
        assert created_itinerary.purpose == "FAMILY"
        assert created_itinerary.styles == ["NATURE", "FOOD"]
        assert created_itinerary.title == "제주도 3박4일"

    async def test_create_success_with_optional_fields_omitted(
        self, mock_itinerary_repo, sample_user_id
    ):
        mock_itinerary_repo.create.side_effect = _fake_saved

        service = ItineraryService(mock_itinerary_repo)
        req = ItineraryConditionsRequest(
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 13),
            region="제주도",
            arrival_time="LUNCH",
            departure_time="MORNING",
        )

        await service.create_itinerary(sample_user_id, req)

        created_itinerary = mock_itinerary_repo.create.await_args.args[0]
        assert created_itinerary.transportation is None
        assert created_itinerary.purpose is None
        assert created_itinerary.styles == []


class TestListItineraries:
    async def test_list_returns_owned_itineraries(
        self, mock_itinerary_repo, sample_itinerary, sample_user_id
    ):
        mock_itinerary_repo.find_all_by_user.return_value = [sample_itinerary]

        service = ItineraryService(mock_itinerary_repo)
        result = await service.list_itineraries(sample_user_id)

        assert len(result) == 1
        assert result[0].itinerary_id == sample_itinerary.itinerary_id
        assert result[0].region == "제주도"
        mock_itinerary_repo.find_all_by_user.assert_awaited_once_with(sample_user_id)

    async def test_list_returns_empty_when_no_itineraries(
        self, mock_itinerary_repo, sample_user_id
    ):
        mock_itinerary_repo.find_all_by_user.return_value = []

        service = ItineraryService(mock_itinerary_repo)
        result = await service.list_itineraries(sample_user_id)

        assert result == []


class TestGetItineraryDetail:
    async def test_get_detail_success_with_places(
        self,
        mock_itinerary_repo,
        sample_itinerary,
        sample_place,
        sample_itinerary_place,
        sample_user_id,
    ):
        mock_itinerary_repo.find_by_id.return_value = sample_itinerary
        mock_itinerary_repo.find_places.return_value = [
            (sample_itinerary_place, sample_place)
        ]

        service = ItineraryService(mock_itinerary_repo)
        result = await service.get_itinerary_detail(
            sample_user_id, sample_itinerary.itinerary_id
        )

        assert result.itinerary_id == sample_itinerary.itinerary_id
        assert result.schedule is None
        assert len(result.places) == 1
        assert result.places[0].place_id == "123"
        assert result.conditions.region == "제주도"

    async def test_get_detail_generated_status_builds_schedule_from_places(
        self,
        mock_itinerary_repo,
        sample_itinerary,
        sample_place,
        sample_itinerary_place,
        sample_user_id,
    ):
        sample_itinerary.status = "GENERATED"
        mock_itinerary_repo.find_by_id.return_value = sample_itinerary
        mock_itinerary_repo.find_places.return_value = [
            (sample_itinerary_place, sample_place)
        ]

        service = ItineraryService(mock_itinerary_repo)
        result = await service.get_itinerary_detail(
            sample_user_id, sample_itinerary.itinerary_id
        )

        assert result.schedule is not None
        trip_days = (sample_itinerary.end_date - sample_itinerary.start_date).days + 1
        assert len(result.schedule.days) == trip_days
        day_1 = result.schedule.days[0]
        assert day_1.day == 1
        assert len(day_1.items) == 1
        assert day_1.items[0].place_id == "123"
        assert day_1.items[0].time_slot == "LUNCH"

    async def test_get_detail_draft_status_with_unplaced_places_returns_null_fields(
        self,
        mock_itinerary_repo,
        sample_itinerary,
        sample_place,
        sample_user_id,
    ):
        """담기만 하고 아직 generate 전인 상태 - #7에서 500 나던 케이스."""
        from app.models.itinerary_place import ItineraryPlace

        unplaced = ItineraryPlace(
            itinerary_place_id=uuid.uuid4(),
            itinerary_id=sample_itinerary.itinerary_id,
            place_id="123",
        )
        mock_itinerary_repo.find_by_id.return_value = sample_itinerary
        mock_itinerary_repo.find_places.return_value = [(unplaced, sample_place)]

        service = ItineraryService(mock_itinerary_repo)
        result = await service.get_itinerary_detail(
            sample_user_id, sample_itinerary.itinerary_id
        )

        assert result.schedule is None
        assert result.places[0].day is None
        assert result.places[0].time_slot is None
        assert result.places[0].order_in_day is None

    async def test_get_detail_no_places_returns_empty_list_and_null_schedule(
        self, mock_itinerary_repo, sample_itinerary, sample_user_id
    ):
        mock_itinerary_repo.find_by_id.return_value = sample_itinerary
        mock_itinerary_repo.find_places.return_value = []

        service = ItineraryService(mock_itinerary_repo)
        result = await service.get_itinerary_detail(
            sample_user_id, sample_itinerary.itinerary_id
        )

        assert result.places == []
        assert result.schedule is None

    async def test_get_detail_not_found_raises_404(
        self, mock_itinerary_repo, sample_user_id
    ):
        mock_itinerary_repo.find_by_id.return_value = None

        service = ItineraryService(mock_itinerary_repo)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_itinerary_detail(sample_user_id, uuid.uuid4())

        assert exc_info.value.status_code == 404

    async def test_get_detail_other_users_itinerary_raises_404(
        self, mock_itinerary_repo, sample_itinerary
    ):
        mock_itinerary_repo.find_by_id.return_value = sample_itinerary

        service = ItineraryService(mock_itinerary_repo)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_itinerary_detail(
                uuid.uuid4(), sample_itinerary.itinerary_id
            )

        assert exc_info.value.status_code == 404


class TestDeleteItinerary:
    async def test_delete_success(
        self, mock_itinerary_repo, sample_itinerary, sample_user_id
    ):
        mock_itinerary_repo.find_by_id.return_value = sample_itinerary

        service = ItineraryService(mock_itinerary_repo)
        await service.delete_itinerary(
            sample_itinerary.user_id, sample_itinerary.itinerary_id
        )

        mock_itinerary_repo.delete.assert_awaited_once_with(sample_itinerary)

    async def test_delete_not_found_raises_404(
        self, mock_itinerary_repo, sample_user_id
    ):
        mock_itinerary_repo.find_by_id.return_value = None

        service = ItineraryService(mock_itinerary_repo)

        with pytest.raises(HTTPException) as exc_info:
            await service.delete_itinerary(sample_user_id, uuid.uuid4())

        assert exc_info.value.status_code == 404
        mock_itinerary_repo.delete.assert_not_awaited()

    async def test_delete_other_users_itinerary_raises_404(
        self, mock_itinerary_repo, sample_itinerary
    ):
        mock_itinerary_repo.find_by_id.return_value = sample_itinerary

        service = ItineraryService(mock_itinerary_repo)

        with pytest.raises(HTTPException) as exc_info:
            await service.delete_itinerary(uuid.uuid4(), sample_itinerary.itinerary_id)

        assert exc_info.value.status_code == 404
        mock_itinerary_repo.delete.assert_not_awaited()
