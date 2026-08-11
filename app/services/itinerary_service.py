from collections import defaultdict
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException, status

from app.models.itinerary import Itinerary
from app.models.itinerary_place import ItineraryPlace
from app.models.place import Place
from app.repositories.itinerary_repository import ItineraryRepository
from app.schemas.itinerary import (
    ItineraryConditionsRequest,
    ItineraryConditionsResponse,
    ItineraryCreateResponse,
    ItineraryDetailResponse,
    ItineraryPlaceResponse,
    ItinerarySummaryResponse,
    ScheduleDayResponse,
    ScheduleItemResponse,
    ScheduleResponse,
)
from app.utils.itinerary_title import generate_itinerary_title
from app.utils.region_thumbnail import get_region_thumbnail


class ItineraryService:
    def __init__(self, repo: ItineraryRepository):
        self.repo = repo

    async def create_itinerary(
        self, user_id: UUID, req: ItineraryConditionsRequest
    ) -> ItineraryCreateResponse:
        itinerary = Itinerary(
            user_id=user_id,
            title=generate_itinerary_title(req.region, req.start_date, req.end_date),
            status="DRAFT",
            region=req.region,
            start_date=req.start_date,
            end_date=req.end_date,
            arrival_time=req.arrival_time,
            departure_time=req.departure_time,
            transportation=req.transportation,
            purpose=req.purpose,
            styles=req.styles,
        )
        created = await self.repo.create(itinerary)
        return ItineraryCreateResponse(
            itinerary_id=created.itinerary_id,
            status=created.status,
            created_at=created.created_at,
        )

    async def list_itineraries(self, user_id: UUID) -> list[ItinerarySummaryResponse]:
        itineraries = await self.repo.find_all_by_user(user_id)
        return [
            ItinerarySummaryResponse(
                itinerary_id=itinerary.itinerary_id,
                title=itinerary.title,
                region=itinerary.region,
                start_date=itinerary.start_date,
                end_date=itinerary.end_date,
                status=itinerary.status,
                thumbnail_url=get_region_thumbnail(itinerary.region),
                updated_at=itinerary.updated_at,
            )
            for itinerary in itineraries
        ]

    async def get_itinerary_detail(
        self, user_id: UUID, itinerary_id: UUID
    ) -> ItineraryDetailResponse:
        itinerary = await self._get_owned_itinerary(user_id, itinerary_id)
        place_rows = await self.repo.find_places(itinerary_id)

        places = [
            ItineraryPlaceResponse(
                place_id=place.place_id,
                name=place.name,
                category=place.category,
                day=itinerary_place.day,
                time_slot=itinerary_place.time_slot,
                order_in_day=itinerary_place.order_in_day,
                lat=place.lat,
                lng=place.lng,
            )
            for itinerary_place, place in place_rows
        ]

        schedule = None
        if itinerary.status in ("GENERATED", "SAVED"):
            schedule = self._build_schedule(itinerary, place_rows)

        return ItineraryDetailResponse(
            itinerary_id=itinerary.itinerary_id,
            status=itinerary.status,
            conditions=ItineraryConditionsResponse.model_validate(itinerary),
            places=places,
            schedule=schedule,
            updated_at=itinerary.updated_at,
        )

    def _build_schedule(
        self,
        itinerary: Itinerary,
        place_rows: list[tuple[ItineraryPlace, Place]],
    ) -> ScheduleResponse:
        """day별로 그룹핑해 ScheduleResponse를 조립한다.

        place_rows는 이미 day/time_slot/order_in_day 기준으로 정렬되어 있다
        (ItineraryRepository.find_places).
        """
        items_by_day: dict[int, list[ScheduleItemResponse]] = defaultdict(list)
        for itinerary_place, place in place_rows:
            if itinerary_place.day is None:
                continue
            items_by_day[itinerary_place.day].append(
                ScheduleItemResponse(
                    place_id=place.place_id,
                    name=place.name,
                    time_slot=itinerary_place.time_slot,
                    start_time=itinerary_place.start_time,
                    order_in_day=itinerary_place.order_in_day,
                    travel_time_to_next_min=itinerary_place.travel_time_to_next_min,
                )
            )

        num_days = (itinerary.end_date - itinerary.start_date).days + 1
        days = [
            ScheduleDayResponse(
                day=day,
                date=itinerary.start_date + timedelta(days=day - 1),
                items=items_by_day.get(day, []),
            )
            for day in range(1, num_days + 1)
        ]
        return ScheduleResponse(days=days)

    async def delete_itinerary(self, user_id: UUID, itinerary_id: UUID) -> None:
        itinerary = await self._get_owned_itinerary(user_id, itinerary_id)
        await self.repo.delete(itinerary)

    async def _get_owned_itinerary(
        self, user_id: UUID, itinerary_id: UUID
    ) -> Itinerary:
        itinerary = await self.repo.find_by_id(itinerary_id)
        if itinerary is None or itinerary.user_id != user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "일정을 찾을 수 없습니다.")
        return itinerary
