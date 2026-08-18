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


# ------------------------------------------------------------------
# 슬롯/일차 이동 PATCH /itineraries/{iId}/places/{placeId}
# ------------------------------------------------------------------
class ItineraryPlaceMoveRequest(BaseModel):
    """아이템을 다른 날짜/시간대로 이동.

    order_in_day는 서버가 이동 대상 슬롯 맨 뒤로 자동 배치하므로
    클라이언트가 지정하지 않는다.
    """

    day: int = Field(ge=1)
    time_slot: TimeSlot


# ------------------------------------------------------------------
# 같은 슬롯 내 순서 재정렬 PATCH /itineraries/{iId}/places/reorder
# ------------------------------------------------------------------
class ItineraryPlaceReorderRequest(BaseModel):
    """같은 day/time_slot 안에서 order_in_day를 배열 순서대로 재부여.

    place_ids는 해당 슬롯에 이미 존재하는 아이템들의 place_id를
    원하는 순서대로 전부 나열한 것이어야 한다 (누락/추가 불가).
    실제 일치 여부 검증은 service 레이어에서 처리.
    """

    day: int = Field(ge=1)
    time_slot: TimeSlot
    place_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_place_ids(self) -> "ItineraryPlaceReorderRequest":
        if len(self.place_ids) != len(set(self.place_ids)):
            raise ValueError("place_ids에 중복된 값이 있습니다.")
        return self


# move/reorder 응답은 기존 ItineraryPlaceResponse 재사용
# - move: 이동된 아이템 하나 -> ItineraryPlaceResponse
# - reorder: 재정렬된 슬롯 전체 -> list[ItineraryPlaceResponse]
