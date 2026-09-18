from pydantic import BaseModel


class TourApiPlaceRaw(BaseModel):
    """areaBasedList2 응답 파싱 결과"""

    content_id: str
    name: str
    content_type_id: str  # 12=관광지, 14=문화시설, 15=축제, 28=레포츠
    address: str | None
    lat: float
    lng: float
    thumbnail_url: str | None


class TourApiSearchResult(BaseModel):
    places: list[TourApiPlaceRaw]
    total_count: int
