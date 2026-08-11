from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.models.itinerary_place import ItineraryPlace
from app.models.place import Place
from app.repositories.itinerary_place_repository import ItineraryPlaceRepository


class ItineraryPlaceService:
    def __init__(self, repo: ItineraryPlaceRepository):
        self.repo = repo

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
            return await self.repo.create_itinerary_place(
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

    async def remove_place_from_itinerary(
        self, itinerary_id: UUID, itinerary_place_id: UUID
    ) -> None:
        itinerary_place = await self.repo.get_itinerary_place(itinerary_place_id)
        if itinerary_place is None or itinerary_place.itinerary_id != itinerary_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="담긴 장소를 찾을 수 없습니다.",
            )

        await self.repo.delete_itinerary_place(itinerary_place)
