from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kakao_client import KakaoMapClient, KakaoMobilityClient
from app.db.session import get_db  # 실제 프로젝트 경로에 맞게 수정 필요
from app.repositories.itinerary_place_repository import ItineraryPlaceRepository
from app.schemas.itinerary_place_schema import (
    ItineraryPlaceCreateRequest,
    ItineraryPlaceResponse,
    PlaceCategory,
    PlaceRecommendResponse,
)
from app.services.itinerary_place_service import ItineraryPlaceService

router = APIRouter(
    prefix="/itineraries/{itinerary_id}/places", tags=["itinerary_places"]
)


def get_itinerary_place_service(
    db: AsyncSession = Depends(get_db),
) -> ItineraryPlaceService:
    return ItineraryPlaceService(
        ItineraryPlaceRepository(db), KakaoMapClient(), KakaoMobilityClient()
    )


@router.get("/recommend", response_model=PlaceRecommendResponse)
async def recommend_places(
    itinerary_id: UUID,
    category: Optional[PlaceCategory] = Query(default=None),
    service: ItineraryPlaceService = Depends(get_itinerary_place_service),
) -> PlaceRecommendResponse:
    """지역/목적/스타일 기반으로 아직 담기지 않은 장소를 추천한다."""
    places = await service.get_place_recommendations(itinerary_id, category=category)
    return PlaceRecommendResponse(places=places)


@router.post(
    "",
    response_model=ItineraryPlaceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_place(
    itinerary_id: UUID,
    payload: ItineraryPlaceCreateRequest,
    service: ItineraryPlaceService = Depends(get_itinerary_place_service),
) -> ItineraryPlaceResponse:
    """일정에 장소를 담는다.

    payload에 day/time_slot/order_in_day가 없으면 미배치(NULL) 상태로,
    있으면 배치된 상태로 생성한다 (PlanPage에서 특정 슬롯에 바로 담을 때 사용).
    """
    return await service.add_place_to_itinerary(
        itinerary_id,
        payload.place_id,
        day=payload.day,
        time_slot=payload.time_slot,
        order_in_day=payload.order_in_day,
    )


@router.delete(
    "/{itinerary_place_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_place(
    itinerary_id: UUID,
    itinerary_place_id: UUID,
    service: ItineraryPlaceService = Depends(get_itinerary_place_service),
) -> None:
    """itinerary_place_id 기준으로 담긴 장소를 제거한다."""
    await service.remove_place_from_itinerary(itinerary_id, itinerary_place_id)
