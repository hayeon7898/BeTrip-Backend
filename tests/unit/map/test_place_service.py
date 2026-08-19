from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.schemas.place import KakaoSearchResult, PlaceDetailResponse
from app.services.place_service import PlaceService


async def test_get_place_detail_returns_cached_place(
    mock_place_repo, mock_kakao_client, sample_place
):
    mock_place_repo.get_by_id.return_value = sample_place

    service = PlaceService(mock_place_repo, mock_kakao_client)
    result = await service.get_place_detail("123")

    assert isinstance(result, PlaceDetailResponse)
    assert result.place_id == "123"
    assert result.name == "흑돼지식당"
    assert result.place_url == "https://place.map.kakao.com/123"
    mock_place_repo.get_by_id.assert_awaited_once_with("123")


async def test_get_place_detail_raises_404_when_not_cached(
    mock_place_repo, mock_kakao_client
):
    mock_place_repo.get_by_id.return_value = None

    service = PlaceService(mock_place_repo, mock_kakao_client)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_place_detail("unknown")

    assert exc_info.value.status_code == 404


async def test_search_places_with_keyword_upserts_and_returns_result(
    mock_place_repo, mock_kakao_client, sample_kakao_place_raw, monkeypatch
):
    mock_kakao_client.search_by_keyword.return_value = KakaoSearchResult(
        places=[sample_kakao_place_raw], is_end=True
    )
    monkeypatch.setattr(
        "app.services.place_service.fetch_og_image",
        AsyncMock(return_value="https://example.com/thumb.jpg"),
    )

    service = PlaceService(mock_place_repo, mock_kakao_client)
    result = await service.search_places(
        q="흑돼지", x=None, y=None, radius=None, rect=None, category=None
    )

    assert len(result.places) == 1
    assert result.places[0].place_id == "123"
    assert result.places[0].thumbnail_url == "https://example.com/thumb.jpg"
    assert result.has_next is False
    mock_kakao_client.search_by_keyword.assert_awaited_once()
    mock_place_repo.upsert_many.assert_awaited_once()


async def test_search_places_passes_page_and_reflects_has_next(
    mock_place_repo, mock_kakao_client, sample_kakao_place_raw, monkeypatch
):
    mock_kakao_client.search_by_keyword.return_value = KakaoSearchResult(
        places=[sample_kakao_place_raw], is_end=False
    )
    monkeypatch.setattr(
        "app.services.place_service.fetch_og_image",
        AsyncMock(return_value=None),
    )

    service = PlaceService(mock_place_repo, mock_kakao_client)
    result = await service.search_places(
        q="흑돼지", x=None, y=None, radius=None, rect=None, category=None, page=2
    )

    assert result.has_next is True
    mock_kakao_client.search_by_keyword.assert_awaited_once_with(
        "흑돼지",
        page=2,
        x=None,
        y=None,
        radius=None,
        rect=None,
        category_group_code=None,
    )


async def test_search_places_category_only_requires_location(
    mock_place_repo, mock_kakao_client
):
    service = PlaceService(mock_place_repo, mock_kakao_client)

    with pytest.raises(HTTPException) as exc_info:
        await service.search_places(
            q=None, x=None, y=None, radius=None, rect=None, category="RESTAURANT"
        )

    assert exc_info.value.status_code == 422
    mock_kakao_client.search_by_category.assert_not_awaited()


async def test_search_places_category_with_location_returns_result(
    mock_place_repo, mock_kakao_client, sample_kakao_place_raw, monkeypatch
):
    mock_kakao_client.search_by_category.return_value = KakaoSearchResult(
        places=[sample_kakao_place_raw], is_end=True
    )
    monkeypatch.setattr(
        "app.services.place_service.fetch_og_image",
        AsyncMock(return_value=None),
    )

    service = PlaceService(mock_place_repo, mock_kakao_client)
    result = await service.search_places(
        q=None, x=127.0, y=37.5, radius=500, rect=None, category="RESTAURANT"
    )

    assert len(result.places) == 1
    mock_kakao_client.search_by_category.assert_awaited_once_with(
        "FD6", x=127.0, y=37.5, radius=500, rect=None, page=1
    )


async def test_search_places_without_q_or_category_raises_422(
    mock_place_repo, mock_kakao_client
):
    service = PlaceService(mock_place_repo, mock_kakao_client)

    with pytest.raises(HTTPException) as exc_info:
        await service.search_places(
            q=None, x=None, y=None, radius=None, rect=None, category=None
        )

    assert exc_info.value.status_code == 422


async def test_search_places_skips_og_fetch_for_already_cached_place(
    mock_place_repo,
    mock_kakao_client,
    sample_place,
    sample_kakao_place_raw,
    monkeypatch,
):
    mock_kakao_client.search_by_keyword.return_value = KakaoSearchResult(
        places=[sample_kakao_place_raw], is_end=True
    )
    mock_place_repo.get_by_ids.return_value = [sample_place]  # thumbnail_url 캐시됨
    fetch_mock = AsyncMock()
    monkeypatch.setattr("app.services.place_service.fetch_og_image", fetch_mock)

    service = PlaceService(mock_place_repo, mock_kakao_client)
    result = await service.search_places(
        q="흑돼지", x=None, y=None, radius=None, rect=None, category=None
    )

    fetch_mock.assert_not_awaited()
    assert result.places[0].thumbnail_url == sample_place.thumbnail_url
    assert service.last_cache_stats == {"hit": 1, "miss": 0}


async def test_search_places_fetches_og_image_when_not_cached(
    mock_place_repo, mock_kakao_client, sample_kakao_place_raw, monkeypatch
):
    mock_kakao_client.search_by_keyword.return_value = KakaoSearchResult(
        places=[sample_kakao_place_raw], is_end=True
    )
    mock_place_repo.get_by_ids.return_value = []  # 캐시 없음
    fetch_mock = AsyncMock(return_value="https://example.com/thumb.jpg")
    monkeypatch.setattr("app.services.place_service.fetch_og_image", fetch_mock)

    service = PlaceService(mock_place_repo, mock_kakao_client)
    result = await service.search_places(
        q="흑돼지", x=None, y=None, radius=None, rect=None, category=None
    )

    fetch_mock.assert_awaited_once_with(sample_kakao_place_raw.place_url)
    assert result.places[0].thumbnail_url == "https://example.com/thumb.jpg"
    assert service.last_cache_stats == {"hit": 0, "miss": 1}
