from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.kakao_client import KakaoMapClient, KakaoMobilityClient
from app.models.itinerary import Itinerary
from app.models.itinerary_place import ItineraryPlace
from app.models.place import Place
from app.repositories.itinerary_place_repository import ItineraryPlaceRepository
from app.utils.itinerary_planner import PlaceCoord, compute_start_times


class ItineraryPlaceService:
    def __init__(
        self,
        repo: ItineraryPlaceRepository,
        kakao_map_client: KakaoMapClient,
        kakao_mobility_client: KakaoMobilityClient,
    ):
        self.repo = repo
        self.kakao_map_client = kakao_map_client
        self.kakao_mobility_client = kakao_mobility_client

    async def get_place_recommendations(
        self, itinerary_id: UUID, category: Optional[str] = None
    ) -> list[Place]:
        itinerary = await self.repo.get_itinerary(itinerary_id)
        if itinerary is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="일정을 찾을 수 없습니다."
            )

        exclude_place_ids = await self.repo.get_existing_place_ids(itinerary_id)

        return await self.repo.get_recommended_places(
            region=itinerary.region,
            exclude_place_ids=exclude_place_ids,
            category=category,
        )

    async def add_place_to_itinerary(
        self,
        itinerary_id: UUID,
        place_id: str,
        day: Optional[int] = None,
        time_slot: Optional[str] = None,
        order_in_day: Optional[int] = None,
    ) -> ItineraryPlace:
        itinerary = await self.repo.get_itinerary(itinerary_id)
        if itinerary is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="일정을 찾을 수 없습니다."
            )

        place = await self.repo.get_place(place_id)
        if place is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="존재하지 않는 장소입니다.",
            )

        existing = await self.repo.get_itinerary_place_by_place_id(
            itinerary_id, place_id
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="이미 담긴 장소입니다."
            )

        if day is not None and time_slot is not None and order_in_day is not None:
            slot_conflict = await self.repo.get_itinerary_place_by_slot(
                itinerary_id, day, time_slot, order_in_day
            )
            if slot_conflict is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="이미 해당 시간대에 다른 장소가 배치되어 있습니다.",
                )

        try:
            created = await self.repo.create_itinerary_place(
                itinerary_id,
                place_id,
                day=day,
                time_slot=time_slot,
                order_in_day=order_in_day,
            )
        except IntegrityError:
            # 사전 체크와 실제 insert 사이 경합(race condition)으로
            # unique 제약을 위반한 경우의 안전망
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 담겼거나 같은 시간대에 다른 장소가 배치되어 있습니다.",
            )

        # day/time_slot/order_in_day가 함께 왔을 때(=PlanPage에서 바로 배치)만
        # 인접 구간 이동시간·하루 전체 시작시각을 계산해서 같은 흐름으로 반영한다.
        # PlacePage처럼 미배치 상태로 담기만 하는 경우(day=None)는 "일정"이라는
        # 개념이 없으므로 자연히 스킵된다.
        if day is not None:
            await self._recalculate_day_schedule_after_add(itinerary, created)
            # update_day_schedule의 커밋으로 updated_at이 서버에서 재계산돼
            # expire되므로, 응답 직렬화 전에 최신 값을 동기적으로 채워둔다.
            await self.repo.refresh_itinerary_place(created)

        return created

    async def remove_place_from_itinerary(
        self, itinerary_id: UUID, itinerary_place_id: UUID
    ) -> None:
        itinerary_place = await self.repo.get_itinerary_place(itinerary_place_id)
        if itinerary_place is None or itinerary_place.itinerary_id != itinerary_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="담긴 장소를 찾을 수 없습니다.",
            )

        day = itinerary_place.day
        travel_updates: list[tuple[ItineraryPlace, Optional[int]]] = []
        start_time_updates: list[tuple[ItineraryPlace, str]] = []

        if day is not None:
            itinerary = await self.repo.get_itinerary(itinerary_id)
            day_places = await self.repo.find_day_places_ordered(itinerary_id, day)
            index = next(
                i
                for i, (ip, _) in enumerate(day_places)
                if ip.itinerary_place_id == itinerary_place_id
            )
            prev_entry = day_places[index - 1] if index > 0 else None
            next_entry = day_places[index + 1] if index < len(day_places) - 1 else None

            if prev_entry is not None:
                prev_ip, prev_place = prev_entry
                if next_entry is not None:
                    _, next_place = next_entry
                    mode = "CAR" if itinerary.transportation == "CAR" else "WALK"
                    minutes = await self._try_compute_segment_minutes(
                        prev_place, next_place, mode
                    )
                else:
                    # 삭제되는 항목이 그 날의 마지막이었으면, 이전 항목도 이제
                    # 마지막이 되므로 다음 구간 이동시간을 비운다.
                    minutes = None
                prev_ip.travel_time_to_next_min = minutes
                travel_updates.append((prev_ip, minutes))

            # 삭제된 항목이 빠지면 그 뒤 항목들의 시작시각이 전부 당겨질 수 있으므로
            # 남는 항목 전체를 기준으로 하루 시작시각을 다시 계산한다.
            remaining = [entry for i, entry in enumerate(day_places) if i != index]
            start_time_updates = self._compute_start_time_updates(remaining)

        await self.repo.delete_itinerary_place(itinerary_place)

        if day is not None:
            await self.repo.update_day_schedule(travel_updates, start_time_updates)

    async def _recalculate_day_schedule_after_add(
        self, itinerary: Itinerary, created: ItineraryPlace
    ) -> None:
        day_places = await self.repo.find_day_places_ordered(
            itinerary.itinerary_id, created.day
        )
        index = next(
            i
            for i, (ip, _) in enumerate(day_places)
            if ip.itinerary_place_id == created.itinerary_place_id
        )
        mode = "CAR" if itinerary.transportation == "CAR" else "WALK"
        travel_updates: list[tuple[ItineraryPlace, Optional[int]]] = []

        if index > 0:
            prev_ip, prev_place = day_places[index - 1]
            _, new_place = day_places[index]
            minutes = await self._try_compute_segment_minutes(
                prev_place, new_place, mode
            )
            prev_ip.travel_time_to_next_min = minutes
            travel_updates.append((prev_ip, minutes))

        if index < len(day_places) - 1:
            _, new_place = day_places[index]
            next_ip, next_place = day_places[index + 1]
            minutes = await self._try_compute_segment_minutes(
                new_place, next_place, mode
            )
            created.travel_time_to_next_min = minutes
            travel_updates.append((created, minutes))

        # 삽입 위치 때문에 뒤 항목들의 시작시각도 밀릴 수 있으므로 하루 전체를
        # 기준으로 다시 계산한다 (자동생성 때와 같은 compute_start_times 재사용).
        start_time_updates = self._compute_start_time_updates(day_places)
        await self.repo.update_day_schedule(travel_updates, start_time_updates)

    @staticmethod
    def _compute_start_time_updates(
        day_places: list[tuple[ItineraryPlace, Place]],
    ) -> list[tuple[ItineraryPlace, str]]:
        """day_places 순서(하루 시간 순)를 기준으로, 이미 반영된
        travel_time_to_next_min 값을 그대로 사용해 시작시각을 다시 계산한다."""
        if not day_places:
            return []
        slotted = [
            (
                PlaceCoord(
                    key=str(ip.itinerary_place_id), lat=place.lat, lng=place.lng
                ),
                ip.time_slot,
            )
            for ip, place in day_places
        ]
        travel_minutes = [ip.travel_time_to_next_min for ip, _ in day_places]
        start_times = compute_start_times(slotted, travel_minutes)
        return [
            (ip, start_time) for (ip, _), start_time in zip(day_places, start_times)
        ]

    async def _try_compute_segment_minutes(
        self, origin: Place, destination: Place, mode: str
    ) -> Optional[int]:
        """이동시간 계산을 시도하고, 외부 API(Kakao) 실패 시 담기/삭제 자체는
        실패시키지 않고 None으로 남긴다."""
        try:
            if mode == "CAR":
                route = await self.kakao_mobility_client.get_driving_route(
                    origin.lng, origin.lat, destination.lng, destination.lat
                )
            else:
                route = await self.kakao_map_client.get_walking_route(
                    origin.lng, origin.lat, destination.lng, destination.lat
                )
            return round(route["duration_sec"] / 60)
        except HTTPException:
            return None
