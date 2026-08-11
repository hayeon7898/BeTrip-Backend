from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kakao_client import KakaoMapClient, KakaoMobilityClient
from app.db.session import get_db
from app.repositories.itinerary_repository import ItineraryRepository
from app.services.itinerary_plan_service import ItineraryPlanService
from app.services.itinerary_service import ItineraryService


def get_itinerary_service(db: AsyncSession = Depends(get_db)) -> ItineraryService:
    return ItineraryService(ItineraryRepository(db))


def get_itinerary_plan_service(
    db: AsyncSession = Depends(get_db),
) -> ItineraryPlanService:
    return ItineraryPlanService(
        ItineraryRepository(db), KakaoMapClient(), KakaoMobilityClient()
    )
