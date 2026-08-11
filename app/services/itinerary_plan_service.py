from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException, status

from app.core.kakao_client import KakaoMapClient, KakaoMobilityClient
from app.models.itinerary import Itinerary
from app.models.itinerary_place import ItineraryPlace
from app.models.place import Place
from app.repositories.itinerary_repository import ItineraryRepository
from app.schemas.itinerary import (
    PlanGenerateResponse,
    PlanSaveResponse,
    ScheduleDayResponse,
    ScheduleItemResponse,
    ScheduleResponse,
)
from app.utils.itinerary_planner import (
    PlaceCoord,
    assign_time_slots,
    cluster_by_day,
    compute_start_times,
    order_within_day,
)


class ItineraryPlanService:
    def __init__(
        self,
        repo: ItineraryRepository,
        kakao_map_client: KakaoMapClient,
        kakao_mobility_client: KakaoMobilityClient,
    ):
        self.repo = repo
        self.kakao_map_client = kakao_map_client
        self.kakao_mobility_client = kakao_mobility_client

    async def generate_plan(
        self, user_id: UUID, itinerary_id: UUID
    ) -> PlanGenerateResponse:
        itinerary = await self._get_owned_itinerary(user_id, itinerary_id)
        place_rows = await self.repo.find_places(itinerary_id)

        if not place_rows:
            return PlanGenerateResponse(
                itinerary_id=itinerary.itinerary_id,
                status=itinerary.status,
                schedule=None,
            )

        num_days = (itinerary.end_date - itinerary.start_date).days + 1
        mode = "CAR" if itinerary.transportation == "CAR" else "WALK"

        coord_by_key: dict[str, tuple[ItineraryPlace, Place]] = {}
        coords: list[PlaceCoord] = []
        for itinerary_place, place in place_rows:
            key = str(itinerary_place.itinerary_place_id)
            coord_by_key[key] = (itinerary_place, place)
            coords.append(PlaceCoord(key=key, lat=place.lat, lng=place.lng))

        clusters = cluster_by_day(coords, num_days)

        assignments: list[tuple[ItineraryPlace, dict]] = []
        schedule_days: list[ScheduleDayResponse] = []

        for day in range(1, num_days + 1):
            day_coords = clusters.get(day, [])
            ordered = order_within_day(day_coords)
            slotted = assign_time_slots(
                ordered,
                is_first_day=(day == 1),
                is_last_day=(day == num_days),
                arrival_time=itinerary.arrival_time,
                departure_time=itinerary.departure_time,
            )

            travel_minutes = await self._compute_travel_minutes(
                [coord for coord, _ in slotted], mode
            )
            start_times = compute_start_times(slotted, travel_minutes)

            items: list[ScheduleItemResponse] = []
            for order_in_day, ((coord, time_slot), start_time, travel) in enumerate(
                zip(slotted, start_times, travel_minutes), start=1
            ):
                itinerary_place, place = coord_by_key[coord.key]
                assignments.append(
                    (
                        itinerary_place,
                        {
                            "day": day,
                            "time_slot": time_slot,
                            "order_in_day": order_in_day,
                            "start_time": start_time,
                            "travel_time_to_next_min": travel,
                        },
                    )
                )
                items.append(
                    ScheduleItemResponse(
                        place_id=place.place_id,
                        name=place.name,
                        time_slot=time_slot,
                        start_time=start_time,
                        order_in_day=order_in_day,
                        travel_time_to_next_min=travel,
                    )
                )

            schedule_days.append(
                ScheduleDayResponse(
                    day=day,
                    date=itinerary.start_date + timedelta(days=day - 1),
                    items=items,
                )
            )

        updated = await self.repo.apply_generated_schedule(
            itinerary, "GENERATED", assignments
        )

        return PlanGenerateResponse(
            itinerary_id=updated.itinerary_id,
            status=updated.status,
            schedule=ScheduleResponse(days=schedule_days),
        )

    async def save_plan(self, user_id: UUID, itinerary_id: UUID) -> PlanSaveResponse:
        itinerary = await self._get_owned_itinerary(user_id, itinerary_id)

        if itinerary.status == "DRAFT":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="먼저 일정을 생성해주세요.",
            )

        if itinerary.status == "GENERATED":
            itinerary = await self.repo.mark_saved(itinerary)

        return PlanSaveResponse(
            itinerary_id=itinerary.itinerary_id,
            status=itinerary.status,
            saved_at=itinerary.updated_at,
        )

    async def _compute_travel_minutes(
        self, ordered_coords: list[PlaceCoord], mode: str
    ) -> list[int | None]:
        """인접한 두 장소 쌍마다 이동시간(분)을 계산한다. 마지막 장소는 None."""
        if len(ordered_coords) <= 1:
            return [None] * len(ordered_coords)

        travel_minutes: list[int | None] = []
        for i in range(len(ordered_coords) - 1):
            origin, destination = ordered_coords[i], ordered_coords[i + 1]
            if mode == "CAR":
                route = await self.kakao_mobility_client.get_driving_route(
                    origin.lng, origin.lat, destination.lng, destination.lat
                )
            else:
                route = await self.kakao_map_client.get_walking_route(
                    origin.lng, origin.lat, destination.lng, destination.lat
                )
            travel_minutes.append(round(route["duration_sec"] / 60))
        travel_minutes.append(None)
        return travel_minutes

    async def _get_owned_itinerary(
        self, user_id: UUID, itinerary_id: UUID
    ) -> Itinerary:
        itinerary = await self.repo.find_by_id(itinerary_id)
        if itinerary is None or itinerary.user_id != user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "일정을 찾을 수 없습니다.")
        return itinerary
