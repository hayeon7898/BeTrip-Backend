import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.schemas.place import KakaoPlaceRaw, KakaoSearchResult
from app.utils.category_mapper import map_kakao_category

KEYWORD_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
CATEGORY_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/category.json"
WALK_ROUTE_URL = "https://dapi.kakao.com/v2/routing/walk"
DRIVING_ROUTE_URL = "https://apis-navi.kakaomobility.com/v1/directions"


class KakaoMapClient:
    """
    카카오 로컬/라우팅 API는 place_id로 단건 상세를 주는 엔드포인트가 없다.
    키워드/카테고리 검색 결과 안에서만 place_id, place_url을 얻을 수 있다.
    그래서 이 클라이언트는 '검색'과 '도보 경로'만 제공하고, 검색 결과를 places
    테이블에 캐시해두는 방식으로 설계한다. (place_id 단건 재조회 API는 존재하지 않음)
    """

    def __init__(self):
        self._headers = {"Authorization": f"KakaoAK {settings.KAKAO_REST_API_KEY}"}

    async def search_by_keyword(
        self,
        query: str,
        page: int = 1,
        size: int = 15,
        x: float | None = None,
        y: float | None = None,
        radius: int | None = None,
        rect: str | None = None,
        category_group_code: str | None = None,
    ) -> KakaoSearchResult:
        params = {"query": query, "page": page, "size": size}
        if x is not None:
            params["x"] = x
        if y is not None:
            params["y"] = y
        if radius is not None:
            params["radius"] = radius
        if rect is not None:
            params["rect"] = rect
        if category_group_code is not None:
            params["category_group_code"] = category_group_code
        return await self._search(KEYWORD_SEARCH_URL, params)

    async def search_by_category(
        self,
        category_group_code: str,
        x: float | None = None,
        y: float | None = None,
        radius: int | None = None,
        rect: str | None = None,
        page: int = 1,
        size: int = 15,
    ) -> KakaoSearchResult:
        """query 없이 카테고리+위치만으로 검색하는 카카오 전용 엔드포인트"""
        params = {
            "category_group_code": category_group_code,
            "page": page,
            "size": size,
        }
        if x is not None:
            params["x"] = x
        if y is not None:
            params["y"] = y
        if radius is not None:
            params["radius"] = radius
        if rect is not None:
            params["rect"] = rect
        return await self._search(CATEGORY_SEARCH_URL, params)

    async def get_walking_route(
        self, start_x: float, start_y: float, end_x: float, end_y: float
    ) -> dict:
        """카카오맵 도보 경로 조회. 응답: duration_sec, distance_m"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(
                    WALK_ROUTE_URL,
                    params={
                        "start_x": start_x,
                        "start_y": start_y,
                        "end_x": end_x,
                        "end_y": end_y,
                    },
                    headers=self._headers,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"카카오맵 도보 경로 API 오류: {e.response.status_code}",
                ) from e
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="카카오맵 도보 경로 API 연결 실패",
                ) from e

            route_props = resp.json()["route"]["properties"]
            return {
                "duration_sec": route_props["totalTime"],
                "distance_m": route_props["totalDistance"],
            }

    async def _search(self, url: str, params: dict) -> KakaoSearchResult:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(url, params=params, headers=self._headers)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"카카오맵 API 오류: {e.response.status_code}",
                ) from e
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="카카오맵 API 연결 실패",
                ) from e

            data = resp.json()
            places = [self._parse(doc) for doc in data.get("documents", [])]
            # is_end가 없으면(예상 못한 응답 형태) 더 없다고 보수적으로 처리
            is_end = data.get("meta", {}).get("is_end", True)
            return KakaoSearchResult(places=places, is_end=is_end)

    def _parse(self, doc: dict) -> KakaoPlaceRaw:
        return KakaoPlaceRaw(
            place_id=doc["id"],
            name=doc["place_name"],
            category=map_kakao_category(doc.get("category_name", "")),
            address=doc.get("road_address_name") or doc.get("address_name"),
            lat=float(doc["y"]),
            lng=float(doc["x"]),
            place_url=doc["place_url"],
        )


class KakaoMobilityClient:
    """카카오모빌리티 자동차 길찾기(Directions) API 프록시"""

    def __init__(self):
        self._headers = {"Authorization": f"KakaoAK {settings.KAKAO_REST_API_KEY}"}

    async def get_driving_route(
        self, origin_x: float, origin_y: float, dest_x: float, dest_y: float
    ) -> dict:
        """응답: duration_sec, distance_m"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(
                    DRIVING_ROUTE_URL,
                    params={
                        "origin": f"{origin_x},{origin_y}",
                        "destination": f"{dest_x},{dest_y}",
                    },
                    headers=self._headers,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"카카오모빌리티 API 오류: {e.response.status_code}",
                ) from e
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="카카오모빌리티 API 연결 실패",
                ) from e

            summary = resp.json()["routes"][0]["summary"]
            return {
                "duration_sec": summary["duration"],
                "distance_m": summary["distance"],
            }
