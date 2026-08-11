from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.itinerary import Itinerary
from app.models.itinerary_place import ItineraryPlace
from app.models.place import Place


class ItineraryPlaceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_itinerary(self, itinerary_id: UUID) -> Optional[Itinerary]:
        return await self.db.get(Itinerary, itinerary_id)

    async def get_existing_place_ids(self, itinerary_id: UUID) -> set[str]:
        """이미 이 일정에 담긴 place_id 목록 (추천 결과에서 제외할 때 사용)"""
        result = await self.db.execute(
            select(ItineraryPlace.place_id).where(
                ItineraryPlace.itinerary_id == itinerary_id
            )
        )
        return set(result.scalars().all())

    async def get_recommended_places(
        self,
        *,
        region: str,
        exclude_place_ids: set[str],
        category: Optional[str] = None,
        limit: int = 20,
    ) -> list[Place]:
        """region 기반 추천 후보 조회. 이미 담긴 장소는 제외.

        NOTE: places 테이블에 별도 region 컬럼이 없어 address LIKE 매칭으로
        임시 구현함. itineraries.region 값과 실제 address 포맷이 맞물리는지
        확인 필요 - 안 맞으면 region 매칭 전략을 다시 정해야 함.
        """
        stmt = select(Place).where(Place.address.ilike(f"%{region}%"))

        if category:
            stmt = stmt.where(Place.category == category)

        if exclude_place_ids:
            stmt = stmt.where(Place.place_id.notin_(exclude_place_ids))

        stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_place(self, place_id: str) -> Optional[Place]:
        """담기 요청의 place_id가 실제 존재하는지 확인할 때 사용.
        map 도메인에 이미 place 조회 레포지토리가 있다면 그쪽 걸 재사용해도 됨."""
        return await self.db.get(Place, place_id)

    async def get_itinerary_place_by_place_id(
        self, itinerary_id: UUID, place_id: str
    ) -> Optional[ItineraryPlace]:
        """중복 담기 체크용 (uq_itinerary_places_place)"""
        result = await self.db.execute(
            select(ItineraryPlace).where(
                ItineraryPlace.itinerary_id == itinerary_id,
                ItineraryPlace.place_id == place_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_itinerary_place_by_slot(
        self, itinerary_id: UUID, day: int, time_slot: str, order_in_day: int
    ) -> Optional[ItineraryPlace]:
        """같은 슬롯(day, time_slot, order_in_day)에 이미 배치된 장소가 있는지 확인
        (uq_itinerary_places_slot 사전 체크용)"""
        result = await self.db.execute(
            select(ItineraryPlace).where(
                ItineraryPlace.itinerary_id == itinerary_id,
                ItineraryPlace.day == day,
                ItineraryPlace.time_slot == time_slot,
                ItineraryPlace.order_in_day == order_in_day,
            )
        )
        return result.scalar_one_or_none()

    async def create_itinerary_place(
        self,
        itinerary_id: UUID,
        place_id: str,
        day: Optional[int] = None,
        time_slot: Optional[str] = None,
        order_in_day: Optional[int] = None,
    ) -> ItineraryPlace:
        """day/time_slot/order_in_day를 같이 주면 배치된 상태로,
        생략하면 NULL(스케줄 미배치) 상태로 생성.

        사전에 서비스 레이어에서 중복 체크를 하더라도, 동시 요청 경합 상황을
        대비해 unique 제약(uq_itinerary_places_place, uq_itinerary_places_slot)
        위반 시 rollback 후 IntegrityError를 그대로 전파한다 - 서비스가 409로 변환.
        """
        itinerary_place = ItineraryPlace(
            itinerary_id=itinerary_id,
            place_id=place_id,
            day=day,
            time_slot=time_slot,
            order_in_day=order_in_day,
        )
        self.db.add(itinerary_place)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise
        await self.db.refresh(itinerary_place)
        return itinerary_place

    async def get_itinerary_place(
        self, itinerary_place_id: UUID
    ) -> Optional[ItineraryPlace]:
        return await self.db.get(ItineraryPlace, itinerary_place_id)

    async def delete_itinerary_place(self, itinerary_place: ItineraryPlace) -> None:
        await self.db.delete(itinerary_place)
        await self.db.commit()
