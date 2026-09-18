from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kakao_client import KakaoMapClient, KakaoMobilityClient
from app.core.tour_api_client import TourApiClient
from app.db.session import get_db
from app.repositories.place_repository import PlaceRepository
from app.schemas.place import PlaceCategory, PlaceDetailResponse, PlaceSearchResponse
from app.schemas.transit import TransitMode, TransitResponse
from app.services.place_service import PlaceService
from app.services.transit_service import TransitService

router = APIRouter(prefix="/map", tags=["map"])


def get_place_service(db: AsyncSession = Depends(get_db)) -> PlaceService:
    return PlaceService(PlaceRepository(db), KakaoMapClient(), TourApiClient())


def get_transit_service(db: AsyncSession = Depends(get_db)) -> TransitService:
    return TransitService(PlaceRepository(db), KakaoMapClient(), KakaoMobilityClient())


@router.get(
    "/places/{place_id}",
    response_model=PlaceDetailResponse,
    summary="Get Place Detail",
)
async def get_place_detail(
    place_id: str,
    service: PlaceService = Depends(get_place_service),
):
    return await service.get_place_detail(place_id)


@router.get(
    "/search",
    response_model=PlaceSearchResponse,
    summary="Search Places",
    description=(
        "**q 또는 category 중 하나는 반드시 있어야 함** — 둘 다 없으면 422.\n\n"
        "- `q`만 사용: 키워드 검색. 위치(x/y/radius, rect)는 선택 — "
        "있으면 주변으로 좁혀서 검색\n"
        "- `q` 없이 `category`만 사용: 카테고리 검색. 이때는 위치가 필수 — "
        "`x`+`y`+`radius` 조합 또는 `rect` 중 하나가 없으면 422\n"
        "- 검색 결과는 자동으로 `places` 테이블에 캐시되어, 이후 "
        "`GET /map/places/{place_id}`·`GET /map/transit`에서 바로 조회 가능"
    ),
)
async def search_places(
    q: str | None = Query(
        default=None, description="검색 키워드 (q 또는 category 필수)"
    ),
    x: float | None = Query(default=None, description="기준 좌표 경도"),
    y: float | None = Query(default=None, description="기준 좌표 위도"),
    radius: int | None = Query(default=None, description="반경(m). x,y와 함께 사용"),
    rect: str | None = Query(
        default=None, description="좌하x,좌하y,우상x,우상y — 지도 화면 영역 기준 검색"
    ),
    category: PlaceCategory | None = Query(
        default=None,
        description="카테고리 (q 또는 category 필수, category만 쓰면 위치 필수)",
    ),
    page: int = Query(
        default=1, ge=1, le=45, description="페이지 번호 (카카오 API 최대 45)"
    ),
    service: PlaceService = Depends(get_place_service),
):
    return await service.search_places(q, x, y, radius, rect, category, page)


@router.get(
    "/search/by-tags",
    response_model=PlaceSearchResponse,
    summary="Search Cached Places by Tags",
    description=(
        "이미 캐시된 places 중 취향 태그로 필터링한다. "
        "카카오 API를 호출하지 않고 DB만 조회하므로, 먼저 `/map/search`로 "
        "해당 지역이 캐싱되어 있어야 결과가 나온다.\n\n"
        "태그는 여러 개 줄 수 있으며, 전달한 태그를 **모두** 가진 장소만 반환된다 "
        "(AND 조건)."
    ),
)
async def search_places_by_tags(
    tags: list[str] = Query(..., description="필터링할 태그 목록 (예: 감성,루프탑)"),
    category: PlaceCategory | None = Query(default=None, description="카테고리 필터"),
    limit: int = Query(default=30, ge=1, le=100),
    service: PlaceService = Depends(get_place_service),
):
    return await service.search_by_tags(category, tags, limit)


@router.get("/transit", response_model=TransitResponse, summary="Calculate Travel Time")
async def get_transit(
    from_place_id: str = Query(alias="from", description="출발지 place_id"),
    to_place_id: str = Query(alias="to", description="도착지 place_id"),
    mode: TransitMode = Query(description="CAR 또는 WALK"),
    service: TransitService = Depends(get_transit_service),
):
    return await service.get_transit(from_place_id, to_place_id, mode)
