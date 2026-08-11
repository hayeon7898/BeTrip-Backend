import uuid
from datetime import date
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.kakao_client import KakaoMapClient, KakaoMobilityClient
from app.models.itinerary_place import ItineraryPlace
from tests.integration.itinerary.conftest import create_itinerary
from tests.integration.map.conftest import create_place


async def add_place_to_itinerary(db_session, itinerary_id, place_id) -> ItineraryPlace:
    ip = ItineraryPlace(itinerary_id=itinerary_id, place_id=place_id)
    db_session.add(ip)
    await db_session.commit()
    await db_session.refresh(ip)
    return ip


class TestGeneratePlanAPI:
    async def test_generate_success_persists_schedule_and_updates_status(
        self, client, db_session, signed_up_user, monkeypatch
    ):
        access_token, user_id = signed_up_user
        itinerary = await create_itinerary(
            db_session,
            user_id,
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
            arrival_time="MORNING",
            departure_time="EVENING",
            transportation="CAR",
        )
        place_a = await create_place(db_session, place_id="plan-a", lat=33.4, lng=126.5)
        place_b = await create_place(
            db_session, place_id="plan-b", lat=33.41, lng=126.51
        )
        await add_place_to_itinerary(
            db_session, itinerary.itinerary_id, place_a.place_id
        )
        await add_place_to_itinerary(
            db_session, itinerary.itinerary_id, place_b.place_id
        )

        monkeypatch.setattr(
            KakaoMobilityClient,
            "get_driving_route",
            AsyncMock(return_value={"duration_sec": 600, "distance_m": 3000}),
        )

        response = await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/plans/generate",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "GENERATED"
        assert body["schedule"]["days"][0]["items"]
        assert len(body["schedule"]["days"][0]["items"]) == 2

        await db_session.refresh(itinerary)
        result = await db_session.execute(
            select(ItineraryPlace).where(
                ItineraryPlace.itinerary_id == itinerary.itinerary_id
            )
        )
        places = result.scalars().all()
        assert all(p.day == 1 for p in places)
        assert all(p.time_slot is not None for p in places)
        assert all(p.order_in_day is not None for p in places)

    async def test_generate_no_places_skips_and_keeps_draft(
        self, client, db_session, signed_up_user
    ):
        access_token, user_id = signed_up_user
        itinerary = await create_itinerary(db_session, user_id)

        response = await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/plans/generate",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "DRAFT"
        assert body["schedule"] is None

    async def test_generate_then_detail_no_longer_500s(
        self, client, db_session, signed_up_user, monkeypatch
    ):
        """#7 버그 재현 시나리오 - 미배치 장소가 있어도 500이 나지 않아야 함."""
        access_token, user_id = signed_up_user
        itinerary = await create_itinerary(
            db_session,
            user_id,
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
            arrival_time="MORNING",
            departure_time="EVENING",
        )
        place = await create_place(db_session, place_id="plan-detail-1")
        await add_place_to_itinerary(db_session, itinerary.itinerary_id, place.place_id)

        # generate 전: 미배치 상태에서도 500이 아니라 200 + null 필드
        pre_response = await client.get(
            f"/api/v1/itineraries/{itinerary.itinerary_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert pre_response.status_code == 200
        assert pre_response.json()["places"][0]["day"] is None

        monkeypatch.setattr(
            KakaoMapClient,
            "get_walking_route",
            AsyncMock(return_value={"duration_sec": 120, "distance_m": 100}),
        )
        gen_response = await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/plans/generate",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert gen_response.status_code == 200

        post_response = await client.get(
            f"/api/v1/itineraries/{itinerary.itinerary_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert post_response.status_code == 200
        assert post_response.json()["schedule"] is not None
        assert post_response.json()["places"][0]["day"] == 1

    async def test_generate_not_found_returns_404(self, client, signed_up_user):
        access_token, _ = signed_up_user

        response = await client.post(
            f"/api/v1/itineraries/{uuid.uuid4()}/plans/generate",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 404

    async def test_generate_without_auth_returns_401(
        self, client, db_session, signed_up_user
    ):
        _, user_id = signed_up_user
        itinerary = await create_itinerary(db_session, user_id)

        response = await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/plans/generate"
        )

        assert response.status_code == 401


class TestSavePlanAPI:
    async def test_save_on_draft_returns_409(self, client, db_session, signed_up_user):
        access_token, user_id = signed_up_user
        itinerary = await create_itinerary(db_session, user_id)

        response = await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/plans/save",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 409

    async def test_save_on_generated_transitions_to_saved(
        self, client, db_session, signed_up_user
    ):
        access_token, user_id = signed_up_user
        itinerary = await create_itinerary(db_session, user_id, status="GENERATED")

        response = await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/plans/save",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "SAVED"
        assert body["saved_at"] is not None

    async def test_save_already_saved_is_idempotent(
        self, client, db_session, signed_up_user
    ):
        access_token, user_id = signed_up_user
        itinerary = await create_itinerary(db_session, user_id, status="SAVED")

        response = await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/plans/save",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "SAVED"

    async def test_save_other_users_itinerary_returns_404(
        self, client, db_session, signed_up_user
    ):
        access_token, _ = signed_up_user

        other_signup = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": f"{uuid.uuid4()}@example.com",
                "password": "Passw0rd!",
                "nickname": "다른사람",
            },
        )
        other_user_id = uuid.UUID(other_signup.json()["user_id"])
        other_user_itinerary = await create_itinerary(
            db_session, other_user_id, status="GENERATED"
        )

        response = await client.post(
            f"/api/v1/itineraries/{other_user_itinerary.itinerary_id}/plans/save",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 404

    async def test_save_without_auth_returns_401(
        self, client, db_session, signed_up_user
    ):
        _, user_id = signed_up_user
        itinerary = await create_itinerary(db_session, user_id)

        response = await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/plans/save"
        )

        assert response.status_code == 401
