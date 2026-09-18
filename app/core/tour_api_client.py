import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.schemas.tour_api import TourApiPlaceRaw, TourApiSearchResult

BASE_URL = "https://apis.data.go.kr/B551011/KorService2"

# 우리가 쓸 카테고리만: 관광지, 문화시설, 축제공연행사, 레포츠
# (음식점 39, 숙박 32는 카카오맵이 담당하므로 제외)
CONTENT_TYPE_IDS = ["12", "14", "15", "28"]


class TourApiClient:
    """
    한국관광공사 국문 관광정보 서비스(TourAPI 4.0) 클라이언트.
    서비스키는 공공데이터포털에서 이미 URL 인코딩된 형태로 발급되므로,
    httpx의 자동 인코딩과 충돌하지 않도록 params가 아니라 URL에 직접 이어붙인다.
    """

    def __init__(self):
        self._service_key = settings.TOUR_API_KEY  # 인코딩된 키 그대로 사용

    async def search_by_area_code(
        self,
        area_code: str,
        content_type_id: str,
        page: int = 1,
        num_of_rows: int = 20,
    ) -> TourApiSearchResult:
        """지역코드 기반 목록 조회 (areaBasedList2)"""
        url = (
            f"{BASE_URL}/areaBasedList2"
            f"?serviceKey={self._service_key}"
            f"&numOfRows={num_of_rows}"
            f"&pageNo={page}"
            f"&MobileOS=ETC"
            f"&MobileApp=TripMate"
            f"&areaCode={area_code}"
            f"&contentTypeId={content_type_id}"
            f"&_type=json"
        )
        return await self._fetch(url)

    async def search_by_location(
        self,
        x: float,
        y: float,
        radius: int = 1500,
        content_type_id: str | None = None,
        page: int = 1,
        num_of_rows: int = 20,
    ) -> TourApiSearchResult:
        """좌표 반경 기반 조회 (locationBasedList2)"""
        url = (
            f"{BASE_URL}/locationBasedList2"
            f"?serviceKey={self._service_key}"
            f"&numOfRows={num_of_rows}"
            f"&pageNo={page}"
            f"&MobileOS=ETC"
            f"&MobileApp=TripMate"
            f"&mapX={x}"
            f"&mapY={y}"
            f"&radius={radius}"
            f"&_type=json"
        )
        if content_type_id:
            url += f"&contentTypeId={content_type_id}"
        return await self._fetch(url)

    async def get_detail_common(self, content_id: str) -> dict:
        """개요(overview) 조회 (detailCommon2) - 태그 파이프라인 확장 시 사용 예정"""
        url = (
            f"{BASE_URL}/detailCommon2"
            f"?serviceKey={self._service_key}"
            f"&contentId={content_id}"
            f"&MobileOS=ETC"
            f"&MobileApp=TripMate"
            f"&defaultYN=Y"
            f"&overviewYN=Y"
            f"&_type=json"
        )
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    async def _fetch(self, url: str) -> TourApiSearchResult:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"TourAPI 오류: {e.response.status_code}",
                ) from e
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="TourAPI 연결 실패",
                ) from e

            data = resp.json()
            body = data.get("response", {}).get("body", {})
            items = body.get("items", {})

            # 결과 0건일 때 items가 빈 문자열("")로 오는 TourAPI 특유의 케이스 처리
            if items == "" or not items:
                return TourApiSearchResult(places=[], total_count=0)

            raw_items = items.get("item", [])
            if isinstance(raw_items, dict):  # 결과 1건일 때 배열이 아니라 객체로 옴
                raw_items = [raw_items]

            places = [self._parse(item) for item in raw_items]
            total_count = body.get("totalCount", 0)
            return TourApiSearchResult(places=places, total_count=total_count)

    def _parse(self, item: dict) -> TourApiPlaceRaw:
        return TourApiPlaceRaw(
            content_id=item["contentid"],
            name=item["title"],
            content_type_id=item["contenttypeid"],
            address=item.get("addr1"),
            lat=float(item["mapy"]),
            lng=float(item["mapx"]),
            thumbnail_url=item.get("firstimage") or None,
        )
