from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.v1.endpoints.itineraries.deps import get_itinerary_plan_service
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.itinerary import PlanGenerateResponse, PlanSaveResponse
from app.services.itinerary_plan_service import ItineraryPlanService

router = APIRouter(prefix="/itineraries/{itinerary_id}/plans", tags=["itinerary_plans"])


@router.post(
    "/generate",
    response_model=PlanGenerateResponse,
    summary="Generate Itinerary Plan",
)
async def generate_plan(
    itinerary_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ItineraryPlanService = Depends(get_itinerary_plan_service),
):
    return await service.generate_plan(current_user.user_id, itinerary_id)


@router.post(
    "/save",
    response_model=PlanSaveResponse,
    summary="Save Itinerary Plan",
)
async def save_plan(
    itinerary_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ItineraryPlanService = Depends(get_itinerary_plan_service),
):
    return await service.save_plan(current_user.user_id, itinerary_id)
