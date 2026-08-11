import uuid

import pytest
from fastapi import HTTPException

from app.services.itinerary_plan_service import ItineraryPlanService
from tests.unit.itinerary_plan.conftest import make_itinerary_place, make_place


@pytest.fixture
def service(mock_itinerary_repo, mock_kakao_map_client, mock_kakao_mobility_client):
    return ItineraryPlanService(
        mock_itinerary_repo, mock_kakao_map_client, mock_kakao_mobility_client
    )


class TestGeneratePlan:
    async def test_itinerary_not_found_raises_404(self, service, mock_itinerary_repo):
        mock_itinerary_repo.find_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.generate_plan(uuid.uuid4(), uuid.uuid4())

        assert exc_info.value.status_code == 404

    async def test_other_users_itinerary_raises_404(
        self, service, mock_itinerary_repo, sample_itinerary
    ):
        mock_itinerary_repo.find_by_id.return_value = sample_itinerary

        with pytest.raises(HTTPException) as exc_info:
            await service.generate_plan(uuid.uuid4(), sample_itinerary.itinerary_id)

        assert exc_info.value.status_code == 404

    async def test_no_places_skips_generation_and_keeps_status(
        self, service, mock_itinerary_repo, sample_itinerary, sample_user_id
    ):
        mock_itinerary_repo.find_by_id.return_value = sample_itinerary
        mock_itinerary_repo.find_places.return_value = []

        result = await service.generate_plan(
            sample_user_id, sample_itinerary.itinerary_id
        )

        assert result.status == "DRAFT"
        assert result.schedule is None
        mock_itinerary_repo.apply_generated_schedule.assert_not_awaited()

    async def test_success_uses_car_mode_and_sets_generated(
        self,
        service,
        mock_itinerary_repo,
        mock_kakao_mobility_client,
        mock_kakao_map_client,
        sample_itinerary,
        sample_user_id,
    ):
        sample_itinerary.transportation = "CAR"
        place_a = make_place("a", 33.4, 126.5)
        place_b = make_place("b", 33.41, 126.51)
        ip_a = make_itinerary_place("a", sample_itinerary.itinerary_id)
        ip_b = make_itinerary_place("b", sample_itinerary.itinerary_id)

        mock_itinerary_repo.find_by_id.return_value = sample_itinerary
        mock_itinerary_repo.find_places.return_value = [
            (ip_a, place_a),
            (ip_b, place_b),
        ]
        mock_kakao_mobility_client.get_driving_route.return_value = {
            "duration_sec": 600,
            "distance_m": 3000,
        }

        def apply_side_effect(itinerary, status, assignments):
            itinerary.status = status
            return itinerary

        mock_itinerary_repo.apply_generated_schedule.side_effect = apply_side_effect

        result = await service.generate_plan(
            sample_user_id, sample_itinerary.itinerary_id
        )

        assert result.status == "GENERATED"
        assert result.schedule is not None
        assert len(result.schedule.days) == 1
        assert len(result.schedule.days[0].items) == 2
        mock_kakao_mobility_client.get_driving_route.assert_awaited_once()
        mock_kakao_map_client.get_walking_route.assert_not_awaited()

        mock_itinerary_repo.apply_generated_schedule.assert_awaited_once()
        _, called_status, assignments = (
            mock_itinerary_repo.apply_generated_schedule.await_args.args
        )
        assert called_status == "GENERATED"
        assert len(assignments) == 2
        days = {fields["day"] for _, fields in assignments}
        assert days == {1}

    async def test_public_transport_falls_back_to_walk_mode(
        self,
        service,
        mock_itinerary_repo,
        mock_kakao_map_client,
        mock_kakao_mobility_client,
        sample_itinerary,
        sample_user_id,
    ):
        sample_itinerary.transportation = "PUBLIC_TRANSPORT"
        place_a = make_place("a", 33.4, 126.5)
        place_b = make_place("b", 33.41, 126.51)
        ip_a = make_itinerary_place("a", sample_itinerary.itinerary_id)
        ip_b = make_itinerary_place("b", sample_itinerary.itinerary_id)

        mock_itinerary_repo.find_by_id.return_value = sample_itinerary
        mock_itinerary_repo.find_places.return_value = [
            (ip_a, place_a),
            (ip_b, place_b),
        ]
        mock_kakao_map_client.get_walking_route.return_value = {
            "duration_sec": 300,
            "distance_m": 400,
        }
        mock_itinerary_repo.apply_generated_schedule.side_effect = (
            lambda itinerary, status, assignments: itinerary
        )

        await service.generate_plan(sample_user_id, sample_itinerary.itinerary_id)

        mock_kakao_map_client.get_walking_route.assert_awaited_once()
        mock_kakao_mobility_client.get_driving_route.assert_not_awaited()

    async def test_regenerate_reverts_saved_status_to_generated(
        self,
        service,
        mock_itinerary_repo,
        mock_kakao_mobility_client,
        sample_itinerary,
        sample_user_id,
    ):
        sample_itinerary.status = "SAVED"
        place_a = make_place("a", 33.4, 126.5)
        ip_a = make_itinerary_place("a", sample_itinerary.itinerary_id)

        mock_itinerary_repo.find_by_id.return_value = sample_itinerary
        mock_itinerary_repo.find_places.return_value = [(ip_a, place_a)]

        def apply_side_effect(itinerary, status, assignments):
            itinerary.status = status
            return itinerary

        mock_itinerary_repo.apply_generated_schedule.side_effect = apply_side_effect

        result = await service.generate_plan(
            sample_user_id, sample_itinerary.itinerary_id
        )

        assert result.status == "GENERATED"

    async def test_external_api_failure_propagates(
        self,
        service,
        mock_itinerary_repo,
        mock_kakao_mobility_client,
        sample_itinerary,
        sample_user_id,
    ):
        sample_itinerary.transportation = "CAR"
        place_a = make_place("a", 33.4, 126.5)
        place_b = make_place("b", 33.41, 126.51)
        ip_a = make_itinerary_place("a", sample_itinerary.itinerary_id)
        ip_b = make_itinerary_place("b", sample_itinerary.itinerary_id)

        mock_itinerary_repo.find_by_id.return_value = sample_itinerary
        mock_itinerary_repo.find_places.return_value = [
            (ip_a, place_a),
            (ip_b, place_b),
        ]
        mock_kakao_mobility_client.get_driving_route.side_effect = HTTPException(
            status_code=502, detail="카카오모빌리티 API 오류"
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.generate_plan(sample_user_id, sample_itinerary.itinerary_id)

        assert exc_info.value.status_code == 502
        mock_itinerary_repo.apply_generated_schedule.assert_not_awaited()


class TestSavePlan:
    async def test_itinerary_not_found_raises_404(self, service, mock_itinerary_repo):
        mock_itinerary_repo.find_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.save_plan(uuid.uuid4(), uuid.uuid4())

        assert exc_info.value.status_code == 404

    async def test_draft_status_raises_409(
        self, service, mock_itinerary_repo, sample_itinerary, sample_user_id
    ):
        sample_itinerary.status = "DRAFT"
        mock_itinerary_repo.find_by_id.return_value = sample_itinerary

        with pytest.raises(HTTPException) as exc_info:
            await service.save_plan(sample_user_id, sample_itinerary.itinerary_id)

        assert exc_info.value.status_code == 409
        mock_itinerary_repo.mark_saved.assert_not_awaited()

    async def test_generated_status_marks_saved(
        self, service, mock_itinerary_repo, sample_itinerary, sample_user_id
    ):
        sample_itinerary.status = "GENERATED"
        mock_itinerary_repo.find_by_id.return_value = sample_itinerary

        async def mark_saved_side_effect(itinerary):
            itinerary.status = "SAVED"
            return itinerary

        mock_itinerary_repo.mark_saved.side_effect = mark_saved_side_effect

        result = await service.save_plan(sample_user_id, sample_itinerary.itinerary_id)

        assert result.status == "SAVED"
        assert result.saved_at == sample_itinerary.updated_at
        mock_itinerary_repo.mark_saved.assert_awaited_once_with(sample_itinerary)

    async def test_already_saved_is_idempotent(
        self, service, mock_itinerary_repo, sample_itinerary, sample_user_id
    ):
        sample_itinerary.status = "SAVED"
        mock_itinerary_repo.find_by_id.return_value = sample_itinerary

        result = await service.save_plan(sample_user_id, sample_itinerary.itinerary_id)

        assert result.status == "SAVED"
        mock_itinerary_repo.mark_saved.assert_not_awaited()
