from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException

from app.core.kakao_client import KakaoMapClient, KakaoMobilityClient
from app.schemas.place import KakaoPlaceRaw


def _fake_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def test_parse_maps_restaurant_document_to_kakao_place_raw():
    client = KakaoMapClient.__new__(KakaoMapClient)
    doc = {
        "id": "123",
        "place_name": "흑돼지식당",
        "category_name": "음식점 > 한식 > 고기",
        "road_address_name": "제주시 어딘가",
        "y": "33.4",
        "x": "126.5",
        "place_url": "http://place.map.kakao.com/123",
    }

    result = client._parse(doc)

    assert isinstance(result, KakaoPlaceRaw)
    assert result.place_id == "123"
    assert result.category == "RESTAURANT"
    assert result.lat == 33.4
    assert result.lng == 126.5
    assert result.place_url == "http://place.map.kakao.com/123"


async def test_search_by_keyword_parses_documents(monkeypatch):
    async def fake_get(self, url, params=None, headers=None):
        return _fake_response(
            {
                "documents": [
                    {
                        "id": "1",
                        "place_name": "테스트카페",
                        "category_name": "카페 > 디저트카페",
                        "road_address_name": "서울시 어딘가",
                        "y": "37.5",
                        "x": "127.0",
                        "place_url": "http://place.map.kakao.com/1",
                    }
                ]
            }
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = KakaoMapClient()
    result = await client.search_by_keyword("테스트")

    assert len(result.places) == 1
    assert result.places[0].category == "CAFE"
    # 응답에 meta가 없으면 더 없다고 보수적으로 처리
    assert result.is_end is True


async def test_search_by_keyword_parses_is_end_false_from_meta(monkeypatch):
    async def fake_get(self, url, params=None, headers=None):
        return _fake_response({"documents": [], "meta": {"is_end": False}})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = KakaoMapClient()
    result = await client.search_by_keyword("테스트", page=1)

    assert result.is_end is False


async def test_search_by_keyword_raises_502_on_http_error(monkeypatch):
    async def fake_get(self, url, params=None, headers=None):
        resp = _fake_response({}, status_code=502)
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
        return resp

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = KakaoMapClient()
    with pytest.raises(HTTPException) as exc_info:
        await client.search_by_keyword("테스트")

    assert exc_info.value.status_code == 502


async def test_search_by_keyword_raises_503_on_connection_error(monkeypatch):
    async def fake_get(self, url, params=None, headers=None):
        raise httpx.ConnectError("boom", request=MagicMock())

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = KakaoMapClient()
    with pytest.raises(HTTPException) as exc_info:
        await client.search_by_keyword("테스트")

    assert exc_info.value.status_code == 503


async def test_search_by_category_parses_documents(monkeypatch):
    async def fake_get(self, url, params=None, headers=None):
        assert params["category_group_code"] == "FD6"
        return _fake_response({"documents": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = KakaoMapClient()
    result = await client.search_by_category("FD6", x=127.0, y=37.5, radius=500)

    assert result.places == []


async def test_get_walking_route_parses_duration_and_distance(monkeypatch):
    async def fake_get(self, url, params=None, headers=None):
        return _fake_response(
            {"route": {"properties": {"totalTime": 600, "totalDistance": 1200}}}
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = KakaoMapClient()
    result = await client.get_walking_route(127.0, 37.5, 127.1, 37.6)

    assert result == {"duration_sec": 600, "distance_m": 1200}


async def test_get_driving_route_parses_duration_and_distance(monkeypatch):
    async def fake_get(self, url, params=None, headers=None):
        return _fake_response(
            {"routes": [{"summary": {"duration": 900, "distance": 5000}}]}
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = KakaoMobilityClient()
    result = await client.get_driving_route(127.0, 37.5, 127.1, 37.6)

    assert result == {"duration_sec": 900, "distance_m": 5000}
