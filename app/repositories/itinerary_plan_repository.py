from sqlalchemy.ext.asyncio import AsyncSession

from app.models.itinerary import Itinerary
from app.models.itinerary_place import ItineraryPlace


class ItineraryPlanRepository:
    """ItineraryPlanService(자동생성/저장) 전용 쓰기 로직.

    itinerary/itinerary_place 조회(find_by_id, find_places)는 ItineraryService와도
    공유되는 일반 조회라 ItineraryRepository에 그대로 둔다. 이 repo는 오직
    ItineraryPlanService만 사용하는, 생성/저장 흐름에서만 발생하는 쓰기 작업만 모은다.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def apply_generated_schedule(
        self,
        itinerary: Itinerary,
        status: str,
        assignments: list[tuple[ItineraryPlace, dict]],
    ) -> Itinerary:
        """일정 상태 변경 + itinerary_places 스케줄 필드 갱신을 한 트랜잭션으로 커밋."""
        itinerary.status = status
        for itinerary_place, fields in assignments:
            for key, value in fields.items():
                setattr(itinerary_place, key, value)
        await self.db.commit()
        await self.db.refresh(itinerary)
        return itinerary

    async def mark_saved(self, itinerary: Itinerary) -> Itinerary:
        itinerary.status = "SAVED"
        await self.db.commit()
        await self.db.refresh(itinerary)
        return itinerary
