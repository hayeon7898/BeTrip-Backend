from fastapi import APIRouter

from app.api.v1.endpoints.itineraries import conditions, itineraries, plans

router = APIRouter()

router.include_router(itineraries.router)
router.include_router(conditions.router)
router.include_router(plans.router)
