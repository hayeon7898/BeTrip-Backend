from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.place import PlaceCategory

ItineraryStatus = Literal["DRAFT", "GENERATED", "SAVED"]
TimeSlot = Literal["MORNING", "LUNCH", "EVENING"]
Transportation = Literal["CAR", "PUBLIC_TRANSPORT"]
Purpose = Literal["FRIEND", "FAMILY", "COUPLE", "PET", "PARENTS"]
TravelStyle = Literal["ACTIVITY", "NATURE", "SIGHTSEEING", "RELAXATION", "FOOD"]

_TIME_SLOT_ORDER = {"MORNING": 0, "LUNCH": 1, "EVENING": 2}
MAX_TRIP_DAYS = 14


class ItinerarySummaryResponse(BaseModel):
    itinerary_id: UUID
    title: str | None
    region: str
    start_date: date
    end_date: date
    status: ItineraryStatus
    thumbnail_url: str | None
    updated_at: datetime


class ItineraryListResponse(BaseModel):
    itineraries: list[ItinerarySummaryResponse]


class ItineraryConditionsRequest(BaseModel):
    start_date: date
    end_date: date
    region: str = Field(min_length=1)
    arrival_time: TimeSlot
    departure_time: TimeSlot
    transportation: Transportation | None = None
    purpose: Purpose | None = None
    styles: list[TravelStyle] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dates_and_times(self) -> "ItineraryConditionsRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date는 start_date보다 빠를 수 없습니다.")

        trip_days = (self.end_date - self.start_date).days + 1
        if trip_days > MAX_TRIP_DAYS:
            raise ValueError(f"여행 기간은 최대 {MAX_TRIP_DAYS}일까지 가능합니다.")

        if (
            self.start_date == self.end_date
            and _TIME_SLOT_ORDER[self.arrival_time]
            > _TIME_SLOT_ORDER[self.departure_time]
        ):
            raise ValueError(
                "당일치기 일정은 도착 시간이 출발 시간보다 늦을 수 없습니다."
            )

        return self


class ItineraryCreateResponse(BaseModel):
    itinerary_id: UUID
    status: ItineraryStatus
    created_at: datetime


class ItineraryConditionsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start_date: date
    end_date: date
    region: str
    arrival_time: TimeSlot
    departure_time: TimeSlot
    transportation: Transportation | None
    purpose: Purpose | None
    styles: list[TravelStyle]


class ItineraryPlaceResponse(BaseModel):
    itinerary_place_id: UUID
    place_id: str
    name: str
    category: PlaceCategory
    address: str | None
    thumbnail_url: str | None
    day: int | None
    time_slot: TimeSlot | None
    order_in_day: int | None
    lat: float
    lng: float


class ScheduleItemResponse(BaseModel):
    place_id: str
    name: str
    time_slot: TimeSlot
    start_time: str | None
    order_in_day: int
    travel_time_to_next_min: int | None


class ScheduleDayResponse(BaseModel):
    day: int
    date: date
    items: list[ScheduleItemResponse]


class ScheduleResponse(BaseModel):
    days: list[ScheduleDayResponse]


class ItineraryDetailResponse(BaseModel):
    itinerary_id: UUID
    status: ItineraryStatus
    conditions: ItineraryConditionsResponse
    places: list[ItineraryPlaceResponse]
    schedule: ScheduleResponse | None
    updated_at: datetime
