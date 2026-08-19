from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kakao_client import KakaoMapClient, KakaoMobilityClient
from app.db.session import get_db
from app.repositories.place_repository import PlaceRepository
from app.schemas.place import PlaceCategory, PlaceDetailResponse, PlaceSearchResponse
from app.schemas.transit import TransitMode, TransitResponse
from app.services.place_service import PlaceService
from app.services.transit_service import TransitService
from app.utils.server_timing import format_server_timing

router = APIRouter(prefix="/map", tags=["map"])


def get_place_service(db: AsyncSession = Depends(get_db)) -> PlaceService:
    return PlaceService(PlaceRepository(db), KakaoMapClient())


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
        "`GET /map/places/{place_id}`·`GET /map/transit`에서 바로 조회 가능\n"
        "- `page`로 다음 페이지 조회 가능(카카오 제한 1~45). 응답의 `has_next`가 "
        "`true`면 다음 페이지가 더 있다는 뜻"
    ),
)
async def search_places(
    response: Response,
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
        default=1, ge=1, le=45, description="페이지 번호 (카카오 제한 1~45)"
    ),
    service: PlaceService = Depends(get_place_service),
):
    result = await service.search_places(q, x, y, radius, rect, category, page)
    # 개발용
    # fetch/upsert 단계별 소요시간을 바로 볼 수 있게 표준 Server-Timing 헤더로 노출.
    # og_fetch에 캐시 fit/miss도 노출
    if service.last_timing:
        descriptions = {}
        if service.last_cache_stats:
            stats = service.last_cache_stats
            descriptions["og_fetch"] = f"hit={stats['hit']} miss={stats['miss']}"
        response.headers["Server-Timing"] = format_server_timing(
            service.last_timing, descriptions
        )
    return result


@router.get("/transit", response_model=TransitResponse, summary="Calculate Travel Time")
async def get_transit(
    from_place_id: str = Query(alias="from", description="출발지 place_id"),
    to_place_id: str = Query(alias="to", description="도착지 place_id"),
    mode: TransitMode = Query(description="CAR 또는 WALK"),
    service: TransitService = Depends(get_transit_service),
):
    return await service.get_transit(from_place_id, to_place_id, mode)
