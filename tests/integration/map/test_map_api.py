from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.kakao_client import KakaoMapClient, KakaoMobilityClient
from app.models.place import Place
from app.schemas.place import KakaoPlaceRaw, KakaoSearchResult
from tests.integration.map.conftest import create_place


class TestSearchAPI:
    async def test_search_by_keyword_upserts_places_and_returns_result(
        self, client, db_session, monkeypatch
    ):
        raw = KakaoPlaceRaw(
            place_id="kakao-1",
            name="흑돼지식당",
            category="RESTAURANT",
            address="제주시 어딘가",
            lat=33.4,
            lng=126.5,
            place_url="http://place.map.kakao.com/kakao-1",
        )
        monkeypatch.setattr(
            KakaoMapClient,
            "search_by_keyword",
            AsyncMock(return_value=KakaoSearchResult(places=[raw], is_end=True)),
        )
        monkeypatch.setattr(
            "app.services.place_service.fetch_og_image",
            AsyncMock(return_value="http://example.com/thumb.jpg"),
        )

        response = await client.get("/api/v1/map/search", params={"q": "흑돼지"})

        assert response.status_code == 200
        data = response.json()
        assert data["places"][0]["place_id"] == "kakao-1"
        assert data["places"][0]["thumbnail_url"] == "http://example.com/thumb.jpg"
        assert data["has_next"] is False

        cached = await db_session.execute(
            select(Place).where(Place.place_id == "kakao-1")
        )
        assert cached.scalar_one_or_none() is not None

    async def test_search_then_detail_does_not_404(self, client, monkeypatch):
        raw = KakaoPlaceRaw(
            place_id="kakao-2",
            name="협재해수욕장",
            category="ACTIVITY",
            address="제주시 어딘가",
            lat=33.4,
            lng=126.5,
            place_url="http://place.map.kakao.com/kakao-2",
        )
        monkeypatch.setattr(
            KakaoMapClient,
            "search_by_keyword",
            AsyncMock(return_value=KakaoSearchResult(places=[raw], is_end=True)),
        )
        monkeypatch.setattr(
            "app.services.place_service.fetch_og_image", AsyncMock(return_value=None)
        )

        search_res = await client.get("/api/v1/map/search", params={"q": "협재"})
        assert search_res.status_code == 200

        detail_res = await client.get("/api/v1/map/places/kakao-2")
        assert detail_res.status_code == 200

    async def test_search_with_page_param_forwards_to_kakao_and_reflects_has_next(
        self, client, monkeypatch
    ):
        raw = KakaoPlaceRaw(
            place_id="kakao-3",
            name="협재해수욕장",
            category="ACTIVITY",
            address="제주시 어딘가",
            lat=33.4,
            lng=126.5,
            place_url="http://place.map.kakao.com/kakao-3",
        )
        search_mock = AsyncMock(
            return_value=KakaoSearchResult(places=[raw], is_end=False)
        )
        monkeypatch.setattr(KakaoMapClient, "search_by_keyword", search_mock)
        monkeypatch.setattr(
            "app.services.place_service.fetch_og_image", AsyncMock(return_value=None)
        )

        response = await client.get(
            "/api/v1/map/search", params={"q": "협재", "page": 2}
        )

        assert response.status_code == 200
        assert response.json()["has_next"] is True
        assert search_mock.await_args.kwargs["page"] == 2

    async def test_search_with_page_out_of_kakao_range_returns_422(self, client):
        response = await client.get(
            "/api/v1/map/search", params={"q": "협재", "page": 46}
        )
        assert response.status_code == 422

    async def test_search_without_q_or_category_returns_422(self, client):
        response = await client.get("/api/v1/map/search")
        assert response.status_code == 422

    async def test_search_category_without_location_returns_422(self, client):
        response = await client.get(
            "/api/v1/map/search", params={"category": "RESTAURANT"}
        )
        assert response.status_code == 422


class TestTransitAPI:
    async def test_transit_car_success(self, db_session, client, monkeypatch):
        origin = await create_place(
            db_session, place_id="origin-1", lat=37.5, lng=127.0
        )
        dest = await create_place(db_session, place_id="dest-1", lat=37.6, lng=127.1)
        monkeypatch.setattr(
            KakaoMobilityClient,
            "get_driving_route",
            AsyncMock(return_value={"duration_sec": 600, "distance_m": 5000}),
        )

        response = await client.get(
            "/api/v1/map/transit",
            params={"from": origin.place_id, "to": dest.place_id, "mode": "CAR"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "duration_min": 10,
            "distance_km": 5.0,
            "mode": "CAR",
        }

    async def test_transit_walk_success(self, db_session, client, monkeypatch):
        origin = await create_place(
            db_session, place_id="origin-2", lat=37.5, lng=127.0
        )
        dest = await create_place(db_session, place_id="dest-2", lat=37.6, lng=127.1)
        monkeypatch.setattr(
            KakaoMapClient,
            "get_walking_route",
            AsyncMock(return_value={"duration_sec": 300, "distance_m": 400}),
        )

        response = await client.get(
            "/api/v1/map/transit",
            params={"from": origin.place_id, "to": dest.place_id, "mode": "WALK"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "duration_min": 5,
            "distance_km": 0.4,
            "mode": "WALK",
        }

    async def test_transit_404_when_place_missing(self, client):
        response = await client.get(
            "/api/v1/map/transit",
            params={"from": "missing-1", "to": "missing-2", "mode": "CAR"},
        )
        assert response.status_code == 404
