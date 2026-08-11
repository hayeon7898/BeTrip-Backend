from fastapi import APIRouter, Depends, status

from app.api.v1.endpoints.itineraries.deps import get_itinerary_service
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.itinerary import ItineraryConditionsRequest, ItineraryCreateResponse
from app.services.itinerary_service import ItineraryService

router = APIRouter(prefix="/itineraries", tags=["itinerary_conditions"])


@router.post(
    "/conditions",
    response_model=ItineraryCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Itinerary",
)
async def create_itinerary(
    req: ItineraryConditionsRequest,
    current_user: User = Depends(get_current_user),
    service: ItineraryService = Depends(get_itinerary_service),
):
    return await service.create_itinerary(current_user.user_id, req)
