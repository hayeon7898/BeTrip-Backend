from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kakao_client import KakaoMapClient
from app.core.tour_api_client import TourApiClient
from app.db.session import get_db
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.place_repository import PlaceRepository
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.conversation_service import ConversationService
from app.services.place_service import PlaceService

router = APIRouter(prefix="/itineraries", tags=["chat"])


def get_conversation_service(
    db: AsyncSession = Depends(get_db),
) -> ConversationService:
    place_service = PlaceService(PlaceRepository(db), KakaoMapClient(), TourApiClient())
    return ConversationService(ConversationRepository(db), place_service)


@router.post("/{itinerary_id}/chat", response_model=ChatResponse)
async def chat(
    itinerary_id: str,
    body: ChatRequest,
    service: ConversationService = Depends(get_conversation_service),
):
    return await service.send_message(itinerary_id, body.message)
