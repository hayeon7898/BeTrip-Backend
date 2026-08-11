from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.v1.endpoints.itineraries.deps import get_itinerary_service
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.itinerary import ItineraryDetailResponse, ItineraryListResponse
from app.services.itinerary_service import ItineraryService

router = APIRouter(prefix="/itineraries", tags=["itineraries"])


@router.get("", response_model=ItineraryListResponse, summary="List My Itineraries")
async def list_itineraries(
    current_user: User = Depends(get_current_user),
    service: ItineraryService = Depends(get_itinerary_service),
):
    itineraries = await service.list_itineraries(current_user.user_id)
    return ItineraryListResponse(itineraries=itineraries)


@router.get(
    "/{itinerary_id}",
    response_model=ItineraryDetailResponse,
    summary="Get Itinerary Detail",
)
async def get_itinerary_detail(
    itinerary_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ItineraryService = Depends(get_itinerary_service),
):
    return await service.get_itinerary_detail(current_user.user_id, itinerary_id)


@router.delete(
    "/{itinerary_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Itinerary",
)
async def delete_itinerary(
    itinerary_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ItineraryService = Depends(get_itinerary_service),
):
    await service.delete_itinerary(current_user.user_id, itinerary_id)
