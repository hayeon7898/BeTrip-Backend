from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.itinerary import Itinerary
from app.models.itinerary_place import ItineraryPlace
from app.models.place import Place


class ItineraryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_all_by_user(self, user_id: UUID) -> list[Itinerary]:
        result = await self.db.execute(
            select(Itinerary)
            .where(Itinerary.user_id == user_id)
            .order_by(Itinerary.updated_at.desc())
        )
        return list(result.scalars().all())

    async def find_by_id(self, itinerary_id: UUID) -> Itinerary | None:
        result = await self.db.execute(
            select(Itinerary).where(Itinerary.itinerary_id == itinerary_id)
        )
        return result.scalar_one_or_none()

    async def find_places(
        self, itinerary_id: UUID
    ) -> list[tuple[ItineraryPlace, Place]]:
        result = await self.db.execute(
            select(ItineraryPlace, Place)
            .join(Place, ItineraryPlace.place_id == Place.place_id)
            .where(ItineraryPlace.itinerary_id == itinerary_id)
            .order_by(
                ItineraryPlace.day,
                ItineraryPlace.time_slot,
                ItineraryPlace.order_in_day,
            )
        )
        return [(row[0], row[1]) for row in result.all()]

    async def create(self, itinerary: Itinerary) -> Itinerary:
        self.db.add(itinerary)
        await self.db.commit()
        await self.db.refresh(itinerary)
        return itinerary

    async def delete(self, itinerary: Itinerary) -> None:
        await self.db.delete(itinerary)
        await self.db.commit()
