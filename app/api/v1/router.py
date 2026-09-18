from fastapi import APIRouter

from app.api.v1.endpoints import auth, chat, itineraries, itinerary_place, map

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(itineraries.router)
api_router.include_router(itinerary_place.router)
api_router.include_router(map.router)
api_router.include_router(chat.router)
