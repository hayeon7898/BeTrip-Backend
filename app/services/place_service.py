import asyncio
import time

from fastapi import HTTPException, status

from app.core.kakao_client import KakaoMapClient
from app.core.og_preview_fetcher import fetch_og_image
from app.core.tour_api_client import TourApiClient
from app.repositories.place_repository import PlaceRepository
from app.schemas.place import (
    PlaceCategory,
    PlaceDetailResponse,
    PlaceSearchResponse,
    PlaceSearchResult,
)
from app.utils.category_mapper import map_to_kakao_category_group_code

TOUR_CONTENT_TYPE_IDS = ["12", "14", "15", "28"]  # 관광지, 문화시설, 축제, 레포츠


class PlaceService:
    def __init__(
        self,
        repo: PlaceRepository,
        kakao_client: KakaoMapClient,
        tour_client: TourApiClient | None = None,
    ):
        self.repo = repo
        self.kakao_client = kakao_client
        self.tour_client = tour_client
        self.last_timing: dict[str, float] = {}
        self.last_cache_stats: dict[str, int] = {}

    async def get_place_detail(self, place_id: str) -> PlaceDetailResponse:
        """
        상세 조회. 카카오 재조회 API가 없으므로 search_places가 미리 캐시해둔
        데이터만 읽는다.
        """
        cached = await self.repo.get_by_id(place_id)
        if cached is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="캐시된 장소 정보가 없습니다. 먼저 검색을 통해 조회해주세요.",
            )
        return PlaceDetailResponse.model_validate(cached)

    async def search_places(
        self,
        q: str | None,
        x: float | None,
        y: float | None,
        radius: int | None,
        rect: str | None,
        category: PlaceCategory | None,
        page: int = 1,
    ) -> PlaceSearchResponse:
        category_group_code = (
            map_to_kakao_category_group_code(category) if category else None
        )

        # 1단계: 카카오 검색 (키워드 or 카테고리)
        t0 = time.perf_counter()
        if q:
            search_result = await self.kakao_client.search_by_keyword(
                q,
                page=page,
                x=x,
                y=y,
                radius=radius,
                rect=rect,
                category_group_code=category_group_code,
            )
        elif category:
            if not rect and not (
                x is not None and y is not None and radius is not None
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="위치 정보(x/y/radius 또는 rect)가 필요합니다",
                )
            search_result = await self.kakao_client.search_by_category(
                category_group_code, x=x, y=y, radius=radius, rect=rect, page=page
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="q 또는 category 중 하나는 필요합니다.",
            )
        raw_places = search_result.places
        has_next = not search_result.is_end
        kakao_ms = (time.perf_counter() - t0) * 1000

        # 2단계: 캐시 스킵 — 이미 썸네일이 캐시된 place는 og fetch 대상에서 제외
        t_cache = time.perf_counter()
        cached_places = await self.repo.get_by_ids(
            [place.place_id for place in raw_places]
        )
        cached_thumbnails = {
            place.place_id: place.thumbnail_url
            for place in cached_places
            if place.thumbnail_url
        }
        cache_lookup_ms = (time.perf_counter() - t_cache) * 1000

        # 3단계: 캐시 미스인 place만 og:image 썸네일 병렬 fetch
        t1 = time.perf_counter()
        to_fetch = [
            place for place in raw_places if place.place_id not in cached_thumbnails
        ]
        fetched = await asyncio.gather(
            *(fetch_og_image(place.place_url) for place in to_fetch)
        )
        fetched_thumbnails = dict(
            zip((place.place_id for place in to_fetch), fetched, strict=True)
        )
        thumbnails = [
            cached_thumbnails.get(place.place_id)
            or fetched_thumbnails.get(place.place_id)
            for place in raw_places
        ]
        og_fetch_ms = (time.perf_counter() - t1) * 1000
        self.last_cache_stats = {"hit": len(cached_thumbnails), "miss": len(to_fetch)}

        # 4단계: places 테이블 upsert 캐싱
        t2 = time.perf_counter()
        await self.repo.upsert_many(
            [
                {
                    "place_id": place.place_id,
                    "name": place.name,
                    "category": place.category,
                    "address": place.address,
                    "lat": place.lat,
                    "lng": place.lng,
                    "place_url": place.place_url,
                    "thumbnail_url": thumbnail,
                }
                for place, thumbnail in zip(raw_places, thumbnails, strict=True)
            ]
        )
        upsert_ms = (time.perf_counter() - t2) * 1000

        self.last_timing = {
            "kakao": kakao_ms,
            "cache_lookup": cache_lookup_ms,
            "og_fetch": og_fetch_ms,
            "upsert": upsert_ms,
        }

        return PlaceSearchResponse(
            places=[
                PlaceSearchResult(
                    place_id=place.place_id,
                    name=place.name,
                    category=place.category,
                    address=place.address,
                    lat=place.lat,
                    lng=place.lng,
                    thumbnail_url=thumbnail,
                )
                for place, thumbnail in zip(raw_places, thumbnails, strict=True)
            ],
            has_next=has_next,
        )

    async def search_by_tags(
        self,
        category: PlaceCategory | None,
        tags: list[str],
        limit: int = 30,
    ) -> PlaceSearchResponse:
        places = await self.repo.find_by_tags(
            tags=tags,
            category=category if category else None,  # .value 제거
            limit=limit,
        )
        return PlaceSearchResponse(
            places=[
                PlaceSearchResult(
                    place_id=place.place_id,
                    name=place.name,
                    category=place.category,
                    address=place.address,
                    lat=place.lat,
                    lng=place.lng,
                    thumbnail_url=place.thumbnail_url,
                )
                for place in places
            ],
            has_next=False,
        )

    async def search_by_region_category(
        self, region: str, category: PlaceCategory, radius: int = 1500
    ) -> PlaceSearchResponse:
        x, y = await self.kakao_client.resolve_region_to_coord(region)
        return await self.search_places(
            q=None, x=x, y=y, radius=radius, rect=None, category=category
        )

    async def search_tour_places(
        self, region: str, radius: int = 1500
    ) -> PlaceSearchResponse:
        """
        TourAPI 관광지/문화시설/축제/레포츠 검색 후 places 테이블에 캐싱.
        place_id는 'tour_{contentid}' 형태로 카카오 place_id와 구분한다.
        """
        x, y = await self.kakao_client.resolve_region_to_coord(region)

        all_raw = []
        for content_type_id in TOUR_CONTENT_TYPE_IDS:
            result = await self.tour_client.search_by_location(
                x=x, y=y, radius=radius, content_type_id=content_type_id
            )
            all_raw.extend(result.places)

        # place_url 보강: 카카오 키워드 검색으로 웹뷰 링크 확보 시도 (best-effort)
        rows = []
        for place in all_raw:
            place_url = None
            try:
                kakao_match = await self.kakao_client.search_by_keyword(
                    f"{place.name} {region}", size=1
                )
                if kakao_match.places:
                    place_url = kakao_match.places[0].place_url
            except Exception:
                pass  # 매칭 실패해도 TourAPI 데이터 자체는 저장

            rows.append(
                {
                    "place_id": f"tour_{place.content_id}",
                    "name": place.name,
                    "category": "ACTIVITY",
                    "address": place.address,
                    "lat": place.lat,
                    "lng": place.lng,
                    "place_url": place_url,
                    "thumbnail_url": place.thumbnail_url,
                    "source": "TOUR_API",
                }
            )

        await self.repo.upsert_many(rows)

        return PlaceSearchResponse(
            places=[
                PlaceSearchResult(
                    place_id=row["place_id"],
                    name=row["name"],
                    category=row["category"],
                    address=row["address"],
                    lat=row["lat"],
                    lng=row["lng"],
                    thumbnail_url=row["thumbnail_url"],
                )
                for row in rows
            ],
            has_next=False,
        )
