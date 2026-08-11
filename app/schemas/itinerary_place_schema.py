from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

TimeSlot = Literal["MORNING", "LUNCH", "EVENING"]
PlaceCategory = Literal["RESTAURANT", "CAFE", "ACTIVITY"]


# ------------------------------------------------------------------
# 장소 추천 GET /itineraries/{iId}/places/recommend
# ------------------------------------------------------------------
class RecommendedPlace(BaseModel):
    """places 테이블 기반 추천 결과 아이템"""

    model_config = ConfigDict(from_attributes=True)

    place_id: str
    name: str
    category: PlaceCategory
    address: Optional[str] = None
    lat: float
    lng: float
    thumbnail_url: Optional[str] = None


class PlaceRecommendResponse(BaseModel):
    places: list[RecommendedPlace]


# ------------------------------------------------------------------
# 장소 담기 POST /itineraries/{iId}/places
# ------------------------------------------------------------------
class ItineraryPlaceCreateRequest(BaseModel):
    """일정에 장소를 담는다.

    두 가지 흐름에서 재사용된다.
    - 장소 추천/검색 후 "일단 담기" (PlacePage): day/time_slot/order_in_day 생략
      -> 스케줄 미배치 상태(NULL)로 생성
    - 일정 계획 화면에서 특정 날짜/시간대/순서에 바로 배치 (PlanPage):
      day/time_slot/order_in_day를 함께 전달 -> 배치된 상태로 생성

    day/time_slot/order_in_day는 셋 다 같이 오거나 셋 다 안 와야 한다
    (하나만 오는 어중간한 상태는 허용하지 않음).
    """

    place_id: str
    day: Optional[int] = Field(default=None, ge=1)
    time_slot: Optional[TimeSlot] = None
    order_in_day: Optional[int] = None

    @model_validator(mode="after")
    def validate_schedule_fields_together(self) -> "ItineraryPlaceCreateRequest":
        schedule_fields = (self.day, self.time_slot, self.order_in_day)
        provided = [f is not None for f in schedule_fields]

        if any(provided) and not all(provided):
            raise ValueError(
                "day/time_slot/order_in_day는 셋 다 함께 전달하거나 "
                "셋 다 생략해야 합니다."
            )

        return self


class ItineraryPlaceResponse(BaseModel):
    """itinerary_places 테이블과 1:1 매칭되는 응답.

    day/time_slot/order_in_day는 스케줄 미배치 상태면 null로 내려간다.
    """

    model_config = ConfigDict(from_attributes=True)

    itinerary_place_id: UUID
    itinerary_id: UUID
    place_id: str
    day: Optional[int] = None
    time_slot: Optional[TimeSlot] = None
    order_in_day: Optional[int] = None
    start_time: Optional[str] = None
    travel_time_to_next_min: Optional[int] = None
    added_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------
# 장소 제거 DELETE /itineraries/{iId}/places/{itineraryPlaceId}
# ------------------------------------------------------------------
# 응답 바디 없이 204 No Content로 처리 (별도 스키마 불필요)
