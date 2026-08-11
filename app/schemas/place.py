from typing import Literal

from pydantic import BaseModel, ConfigDict

PlaceCategory = Literal["RESTAURANT", "CAFE", "ACTIVITY"]


class PlaceDetailResponse(BaseModel):
    """
    place_id로 캐시된 장소 상세를 반환한다.
    메뉴/리뷰/평점은 자체 요약 대신 place_url(카카오맵 상세 페이지)을
    클라이언트가 웹뷰/iframe으로 열어서 보여주는 방식으로 대체한다.
    """

    model_config = ConfigDict(from_attributes=True)

    place_id: str
    name: str
    category: PlaceCategory
    address: str | None = None
    lat: float
    lng: float
    place_url: str
    thumbnail_url: str | None = None


class KakaoPlaceRaw(BaseModel):
    """카카오 로컬 API(키워드/카테고리 검색) 원시 응답을 파싱한 결과."""

    place_id: str
    name: str
    category: PlaceCategory
    address: str | None = None
    lat: float
    lng: float
    place_url: str


class PlaceSearchResult(BaseModel):
    """GET /map/search 응답 아이템. snake_case로만 작성 (docs/api-spec.md 원칙)."""

    place_id: str
    name: str
    category: PlaceCategory
    address: str | None = None
    lat: float
    lng: float
    thumbnail_url: str | None = None


class PlaceSearchResponse(BaseModel):
    places: list[PlaceSearchResult]
