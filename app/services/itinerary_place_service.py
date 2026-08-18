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

    # ------------------------------------------------------------
    # 추천
    # ------------------------------------------------------------
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

    # ------------------------------------------------------------
    # 담기 POST
    # ------------------------------------------------------------
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
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 담겼거나 같은 시간대에 다른 장소가 배치되어 있습니다.",
            )

        # day/time_slot/order_in_day가 함께 왔을 때(=PlanPage에서 바로 배치)만
        # day 전체 이동시간·시작시각을 재계산한다. day=None(PlacePage)은 스킵.
        if day is not None:
            await self._recalculate_day(itinerary, day)

        await self.repo.commit()
        await self.repo.refresh_itinerary_place(created)
        return created

    # ------------------------------------------------------------
    # 삭제 DELETE
    # ------------------------------------------------------------
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
        itinerary = (
            await self.repo.get_itinerary(itinerary_id) if day is not None else None
        )

        await self.repo.delete_itinerary_place(itinerary_place)

        if day is not None:
            await self._recalculate_day(itinerary, day)

        await self.repo.commit()

    # ------------------------------------------------------------
    # 슬롯/일차 이동 PATCH /{placeId}
    # ------------------------------------------------------------
    async def move_place(
        self, itinerary_id: UUID, place_id: str, day: int, time_slot: str
    ) -> ItineraryPlace:
        itinerary = await self.repo.get_itinerary(itinerary_id)
        if itinerary is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="일정을 찾을 수 없습니다."
            )

        itinerary_place = await self.repo.get_itinerary_place_by_place_id(
            itinerary_id, place_id
        )
        if itinerary_place is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="담긴 장소를 찾을 수 없습니다.",
            )

        old_day = itinerary_place.day  # 재계산 대상에 포함하기 위해 이동 전 값 보존

        new_order = (
            await self.repo.get_max_order_in_slot(itinerary_id, day, time_slot) + 1
        )
        itinerary_place.day = day
        itinerary_place.time_slot = time_slot
        itinerary_place.order_in_day = new_order
        await self.repo.flush()

        # 원래 있던 day(아이템 빠짐)와 이동한 day(아이템 들어감) 둘 다 재계산.
        # 같은 day 안에서 슬롯만 바뀐 경우엔 자연히 1개로 합쳐짐.
        affected_days = {d for d in (old_day, day) if d is not None}
        for d in affected_days:
            await self._recalculate_day(itinerary, d)

        await self.repo.commit()
        await self.repo.refresh_itinerary_place(itinerary_place)
        return itinerary_place

    # ------------------------------------------------------------
    # 같은 슬롯 내 순서 재정렬 PATCH /reorder
    # ------------------------------------------------------------
    async def reorder_places(
        self, itinerary_id: UUID, day: int, time_slot: str, place_ids: list[str]
    ) -> list[ItineraryPlace]:
        itinerary = await self.repo.get_itinerary(itinerary_id)
        if itinerary is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="일정을 찾을 수 없습니다."
            )

        slot_places = await self.repo.find_slot_places(itinerary_id, day, time_slot)
        slot_by_place_id = {ip.place_id: ip for ip in slot_places}

        # place_ids가 실제 슬롯 아이템과 정확히 일치하는지 검증
        # (누락/추가/중복 전부 차단)
        if len(place_ids) != len(slot_by_place_id) or set(place_ids) != set(
            slot_by_place_id.keys()
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="place_ids가 해당 슬롯의 아이템과 일치하지 않습니다.",
            )

        for order, pid in enumerate(place_ids, start=1):
            slot_by_place_id[pid].order_in_day = order
        await self.repo.flush()

        await self._recalculate_day(itinerary, day)

        await self.repo.commit()
        reordered = [slot_by_place_id[pid] for pid in place_ids]
        for ip in reordered:
            await self.repo.refresh_itinerary_place(ip)
        return reordered

    # ------------------------------------------------------------
    # 공용: day 전체 이동시간 + 시작시각 재계산
    # (담기/삭제/이동/재정렬 전부 이걸로 통일 - 부분 재계산 최적화는 하지 않음)
    # ------------------------------------------------------------
    async def _recalculate_day(self, itinerary: Itinerary, day: int) -> None:
        day_places = await self.repo.find_day_places_ordered(
            itinerary.itinerary_id, day
        )
        mode = "CAR" if itinerary.transportation == "CAR" else "WALK"

        travel_updates: list[tuple[ItineraryPlace, Optional[int]]] = []
        for i in range(len(day_places) - 1):
            ip, place = day_places[i]
            _, next_place = day_places[i + 1]
            minutes = await self._try_compute_segment_minutes(place, next_place, mode)
            ip.travel_time_to_next_min = minutes
            travel_updates.append((ip, minutes))
        if day_places:
            last_ip, _ = day_places[-1]
            last_ip.travel_time_to_next_min = None
            travel_updates.append((last_ip, None))  # 마지막 아이템은 다음 구간 없음

        start_time_updates = self._compute_start_time_updates(day_places)
        await self.repo.update_day_schedule(travel_updates, start_time_updates)

    @staticmethod
    def _compute_start_time_updates(
        day_places: list[tuple[ItineraryPlace, Place]],
    ) -> list[tuple[ItineraryPlace, str]]:
        """day_places 순서(하루 시간 순)를 기준으로, 이미 반영된
        travel_time_to_next_min 값을 그대로 사용해 시작시각을 다시 계산한다.
        (자동생성 API와 동일한 compute_start_times 재사용)"""
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
        """이동시간 계산을 시도하고, 외부 API(Kakao) 실패 시 담기/삭제/이동/재정렬
        자체는 실패시키지 않고 None으로 남긴다."""
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
