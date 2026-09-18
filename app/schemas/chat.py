from pydantic import BaseModel

from app.schemas.place import PlaceCategory


class ChatRequest(BaseModel):
    message: str


class ChatPlaceCard(BaseModel):
    place_id: str
    name: str
    category: str
    address: str | None
    lat: float
    lng: float
    thumbnail_url: str | None
    tags: list[str] = []


class ChatResponse(BaseModel):
    reply: str
    places: list[ChatPlaceCard] = []


class SearchPlacesArgs(BaseModel):
    """LLM이 도구 호출 시 채우는 인자. Gemini function declaration과 1:1 대응."""

    region: str
    category: PlaceCategory
    tags: list[str] = []
