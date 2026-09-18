from google import genai
from google.genai import types

from app.core.config import settings
from app.models.conversation_message import ConversationMessage
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.chat import ChatPlaceCard, ChatResponse
from app.schemas.place_tag import PlaceTag
from app.services.place_service import PlaceService

TAG_TAXONOMY = [tag.value for tag in PlaceTag]

SYSTEM_PROMPT = f"""당신은 여행 계획을 도와주는 TripMate의 어시스턴트입니다.

사용 가능한 도구는 두 가지입니다:
- search_places:
  음식점, 카페 검색 (카카오맵 데이터)
- search_tour_places:
  관광지, 문화시설, 축제, 레포츠 등 볼거리/즐길거리 검색 (관광공사 데이터)

사용자와 대화하며 아래 정보를 파악하세요:
- region: 여행/검색하려는 지역 (예: 홍대, 강남)
- category: search_places를 쓸 경우 RESTAURANT, CAFE 중 하나
- tags: 사용자가 원하는 분위기/취향. 아래 목록 중에서만 고르세요:
  {", ".join(TAG_TAXONOMY)}

규칙:
1. 사용자가 음식점/카페를 찾으면 search_places를, 관광지/볼거리/즐길거리를
   찾으면 search_tour_places를 호출하세요.
2. region과 (search_places의 경우) category가 파악되면 바로 도구를 호출하세요.
   tags는 사용자가 명시적으로 취향을 말했을 때만 채우고, 없으면 빈 배열로 두세요.
3. 사용자의 취향 표현이 태그 목록에 정확히 없으면, 의미가 가장 가까운
   태그로 변환해서 사용하세요 (예: "인적 드문" -> "조용함").
4. region이 불명확하면 도구를 호출하지 말고 먼저 물어보세요.
5. 검색 결과를 근거로만 답변하세요. 존재하지 않는 장소를 언급하지 마세요.
6. 답변은 친근하고 간결한 한국어로 하세요.
"""

SEARCH_PLACES_DECLARATION = types.FunctionDeclaration(
    name="search_places",
    description="지역, 카테고리(음식점/카페), 취향 태그로 장소를 검색한다.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "region": types.Schema(type="STRING", description="지역명, 예: 홍대"),
            "category": types.Schema(type="STRING", enum=["RESTAURANT", "CAFE"]),
            "tags": types.Schema(
                type="ARRAY",
                items=types.Schema(type="STRING", enum=TAG_TAXONOMY),
                description="사용자가 원하는 취향 태그",
            ),
        },
        required=["region", "category"],
    ),
)

SEARCH_TOUR_PLACES_DECLARATION = types.FunctionDeclaration(
    name="search_tour_places",
    description=(
        "관광지, 문화시설, 축제, 레포츠 등 볼거리/즐길거리를 지역 기준으로 검색한다."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "region": types.Schema(type="STRING", description="지역명, 예: 홍대"),
        },
        required=["region"],
    ),
)


class ConversationService:
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        place_service: PlaceService,
    ):
        self.conversation_repo = conversation_repo
        self.place_service = place_service
        self.llm = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def send_message(self, itinerary_id: str, message: str) -> ChatResponse:
        history = await self.conversation_repo.get_history(itinerary_id)
        gemini_history = self._to_gemini_history(history)

        chat = self.llm.aio.chats.create(
            model="gemini-3.6-flash",
            history=gemini_history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[
                    types.Tool(
                        function_declarations=[
                            SEARCH_PLACES_DECLARATION,
                            SEARCH_TOUR_PLACES_DECLARATION,
                        ]
                    )
                ],
            ),
        )

        response = await chat.send_message(message)
        places: list[ChatPlaceCard] = []

        for _ in range(3):
            function_call = self._extract_function_call(response)
            if not function_call:
                break

            if function_call.name == "search_places":
                places = await self._handle_search(function_call.args)
            elif function_call.name == "search_tour_places":
                places = await self._handle_tour_search(function_call.args)
            else:
                break

            function_response_part = types.Part.from_function_response(
                name=function_call.name,
                response={
                    "places": [p.model_dump() for p in places],
                    "count": len(places),
                },
            )
            response = await chat.send_message(function_response_part)

        reply_text = (
            response.text
            or "죄송해요, 지금은 답변을 만들지 못했어요. 다시 한번 말씀해주시겠어요?"
        )

        await self.conversation_repo.add_message(itinerary_id, "user", message)
        await self.conversation_repo.add_message(itinerary_id, "assistant", reply_text)

        return ChatResponse(reply=reply_text, places=places)

    async def _handle_search(self, args: dict) -> list[ChatPlaceCard]:
        region = args["region"]
        category = args["category"]
        tags = args.get("tags", [])

        search_result = await self.place_service.search_by_region_category(
            region, category
        )

        if tags:
            tag_result = await self.place_service.search_by_tags(category, tags)
            places = tag_result.places
        else:
            places = search_result.places

        return [self._to_card(p) for p in places[:5]]

    async def _handle_tour_search(self, args: dict) -> list[ChatPlaceCard]:
        region = args["region"]
        result = await self.place_service.search_tour_places(region)
        return [self._to_card(p) for p in result.places[:5]]

    def _to_card(self, p) -> ChatPlaceCard:
        return ChatPlaceCard(
            place_id=p.place_id,
            name=p.name,
            category=p.category,
            address=p.address,
            lat=p.lat,
            lng=p.lng,
            thumbnail_url=p.thumbnail_url,
            tags=getattr(p, "tags", []),
        )

    def _extract_function_call(self, response) -> types.FunctionCall | None:
        for part in response.candidates[0].content.parts:
            if part.function_call:
                return part.function_call
        return None

    def _to_gemini_history(
        self, messages: list[ConversationMessage]
    ) -> list[types.Content]:
        role_map = {"user": "user", "assistant": "model"}
        return [
            types.Content(
                role=role_map[m.role], parts=[types.Part.from_text(text=m.content)]
            )
            for m in messages
        ]
