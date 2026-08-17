"""장소 담기/제거 API 통합테스트.

day/time_slot/order_in_day가 함께 오는 경우에만 인접 구간 이동시간이
같은 흐름으로 계산되어 저장되는지, DB에 실제로 반영되는지까지 확인한다.
"""

import uuid
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.kakao_client import KakaoMapClient, KakaoMobilityClient
from app.models.itinerary_place import ItineraryPlace
from tests.integration.itinerary.conftest import create_itinerary
from tests.integration.map.conftest import create_place


class TestAddPlaceAPI:
    async def test_add_without_schedule_skips_kakao_call(
        self, client, db_session, signed_up_user, monkeypatch
    ):
        """PlacePage 흐름(day 없이 담기)은 카카오 API를 아예 호출하지 않는다."""
        access_token, user_id = signed_up_user
        itinerary = await create_itinerary(db_session, user_id)
        place = await create_place(db_session, place_id="unplaced-a")

        mock_driving = AsyncMock()
        monkeypatch.setattr(KakaoMobilityClient, "get_driving_route", mock_driving)

        response = await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/places",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"place_id": place.place_id},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["day"] is None
        assert body["travel_time_to_next_min"] is None
        mock_driving.assert_not_awaited()

    async def test_add_with_schedule_persists_adjacent_travel_time(
        self, client, db_session, signed_up_user, monkeypatch
    ):
        access_token, user_id = signed_up_user
        itinerary = await create_itinerary(db_session, user_id, transportation="CAR")
        place_a = await create_place(
            db_session, place_id="atomic-a", lat=33.4, lng=126.5
        )
        place_b = await create_place(
            db_session, place_id="atomic-b", lat=33.41, lng=126.51
        )

        monkeypatch.setattr(
            KakaoMobilityClient,
            "get_driving_route",
            AsyncMock(return_value={"duration_sec": 600, "distance_m": 3000}),
        )

        first_res = await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/places",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "place_id": place_a.place_id,
                "day": 1,
                "time_slot": "MORNING",
                "order_in_day": 1,
            },
        )
        assert first_res.status_code == 201
        # 혼자뿐인 항목이라 이웃이 없어 travel_time_to_next_min은 그대로 null
        assert first_res.json()["travel_time_to_next_min"] is None
        first_id = first_res.json()["itinerary_place_id"]

        second_res = await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/places",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "place_id": place_b.place_id,
                "day": 1,
                "time_slot": "LUNCH",
                "order_in_day": 1,
            },
        )
        assert second_res.status_code == 201
        # 새로 담긴 항목(B)은 하루의 마지막이라 자기 자신의 다음 구간은 없음
        assert second_res.json()["travel_time_to_next_min"] is None

        # 이전 항목(A)의 travel_time_to_next_min이 B로 이어지도록 DB에 갱신되어야 함
        result = await db_session.execute(
            select(ItineraryPlace).where(
                ItineraryPlace.itinerary_place_id == uuid.UUID(first_id)
            )
        )
        refreshed_a = result.scalar_one()
        assert refreshed_a.travel_time_to_next_min == 10

    async def test_add_uses_walk_mode_when_transportation_not_car(
        self, client, db_session, signed_up_user, monkeypatch
    ):
        access_token, user_id = signed_up_user
        itinerary = await create_itinerary(
            db_session, user_id, transportation="PUBLIC_TRANSPORT"
        )
        place_a = await create_place(db_session, place_id="walk-a", lat=33.4, lng=126.5)
        place_b = await create_place(
            db_session, place_id="walk-b", lat=33.41, lng=126.51
        )

        mock_walking = AsyncMock(return_value={"duration_sec": 300, "distance_m": 400})
        mock_driving = AsyncMock()
        monkeypatch.setattr(KakaoMapClient, "get_walking_route", mock_walking)
        monkeypatch.setattr(KakaoMobilityClient, "get_driving_route", mock_driving)

        await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/places",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "place_id": place_a.place_id,
                "day": 1,
                "time_slot": "MORNING",
                "order_in_day": 1,
            },
        )
        await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/places",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "place_id": place_b.place_id,
                "day": 1,
                "time_slot": "LUNCH",
                "order_in_day": 1,
            },
        )

        mock_walking.assert_awaited_once()
        mock_driving.assert_not_awaited()


class TestRemovePlaceAPI:
    async def test_remove_middle_item_reconnects_neighbors_in_db(
        self, client, db_session, signed_up_user, monkeypatch
    ):
        access_token, user_id = signed_up_user
        itinerary = await create_itinerary(db_session, user_id, transportation="CAR")
        place_a = await create_place(db_session, place_id="mid-a", lat=33.4, lng=126.5)
        place_b = await create_place(
            db_session, place_id="mid-b", lat=33.41, lng=126.51
        )
        place_c = await create_place(
            db_session, place_id="mid-c", lat=33.42, lng=126.52
        )

        monkeypatch.setattr(
            KakaoMobilityClient,
            "get_driving_route",
            AsyncMock(return_value={"duration_sec": 600, "distance_m": 3000}),
        )

        async def add(place, order):
            res = await client.post(
                f"/api/v1/itineraries/{itinerary.itinerary_id}/places",
                headers={"Authorization": f"Bearer {access_token}"},
                json={
                    "place_id": place.place_id,
                    "day": 1,
                    "time_slot": "MORNING",
                    "order_in_day": order,
                },
            )
            return res.json()["itinerary_place_id"]

        first_id = await add(place_a, 1)
        middle_id = await add(place_b, 2)
        await add(place_c, 3)

        delete_res = await client.delete(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/places/{middle_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert delete_res.status_code == 204

        result = await db_session.execute(
            select(ItineraryPlace).where(
                ItineraryPlace.itinerary_place_id == uuid.UUID(first_id)
            )
        )
        refreshed_a = result.scalar_one()
        # B가 빠지면서 A -> C 구간으로 재계산되어 저장되어 있어야 함
        assert refreshed_a.travel_time_to_next_min == 10

        deleted = await db_session.get(ItineraryPlace, uuid.UUID(middle_id))
        assert deleted is None

    async def test_remove_unplaced_item_skips_kakao_call(
        self, client, db_session, signed_up_user, monkeypatch
    ):
        access_token, user_id = signed_up_user
        itinerary = await create_itinerary(db_session, user_id)
        place = await create_place(db_session, place_id="unplaced-remove-a")

        mock_driving = AsyncMock()
        monkeypatch.setattr(KakaoMobilityClient, "get_driving_route", mock_driving)

        add_res = await client.post(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/places",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"place_id": place.place_id},
        )
        itinerary_place_id = add_res.json()["itinerary_place_id"]

        delete_res = await client.delete(
            f"/api/v1/itineraries/{itinerary.itinerary_id}/places/{itinerary_place_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert delete_res.status_code == 204
        mock_driving.assert_not_awaited()
