import logging

from fastapi import HTTPException
from google import genai
from google.genai import types

from app.core.config import settings
from app.models.conversation_message import ConversationMessage
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.chat import ChatPlaceCard, ChatResponse
from app.schemas.place_tag import PlaceTag
from app.services.place_service import PlaceService

logger = logging.getLogger(__name__)

TAG_TAXONOMY = [tag.value for tag in PlaceTag]
MAX_TOOL_ROUNDS = 3
MAX_CARDS = 10

SYSTEM_PROMPT = f"""당신은 여행 계획을 도와주는 BeTrip의 어시스턴트입니다.

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
   찾으면 search_tour_places를 호출하세요. 여러 종류를 함께 찾으면
   필요한 도구를 모두 호출하세요.
2. region과 (search_places의 경우) category가 파악되면 바로 도구를 호출하세요.
   tags는 사용자가 명시적으로 취향을 말했을 때만 채우고, 없으면 빈 배열로 두세요.
3. 사용자의 취향 표현이 태그 목록 중 하나와 의미가 같을 때만 그 태그로
   변환하세요 (예: "인적 드문" -> "조용함"). 비슷하기만 하거나 목록에 없는
   취향(예: "가성비", "콘센트 많은")이면 tags를 비워 두세요.
4. region이 불명확하면 도구를 호출하지 말고 먼저 물어보세요.
5. 검색 결과를 근거로만 답변하세요. 존재하지 않는 장소를 언급하지 마세요.
6. 도구 결과의 tag_matched가 false이면, 취향에 맞는 곳은 찾지 못해
   해당 지역의 일반 결과를 보여준다고 밝히세요.
7. 도구 결과에 error가 있으면 그 내용을 바탕으로 사용자에게 다시 물어보세요.
8. 답변은 친근하고 간결한 한국어로 하세요.
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
        "관광지, 문화시설, 축제, 레포츠 등 볼거리/즐길거리를 지역 기준으로 검색한다. "
        "숙소, 날씨, 교통편은 찾을 수 없으므로 이런 요청에는 호출하지 않는다."
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

        for _ in range(MAX_TOOL_ROUNDS):
            function_calls = self._extract_function_calls(response)
            if not function_calls:
                break

            # 한 응답에 도구 호출이 여러 개일 수 있다 ("관광지랑 맛집 둘 다").
            # 핸들러들이 같은 AsyncSession을 쓰므로 gather 대신 순차 실행한다.
            response_parts = []
            for function_call in function_calls:
                cards, payload = await self._execute_tool(function_call)
                places.extend(cards)
                response_parts.append(
                    types.Part.from_function_response(
                        name=function_call.name, response=payload
                    )
                )
            response = await chat.send_message(response_parts)

        reply_text = (
            response.text
            or "죄송해요, 지금은 답변을 만들지 못했어요. 다시 한번 말씀해주시겠어요?"
        )

        await self.conversation_repo.add_message(itinerary_id, "user", message)
        await self.conversation_repo.add_message(itinerary_id, "assistant", reply_text)

        return ChatResponse(reply=reply_text, places=self._dedupe(places)[:MAX_CARDS])

    async def _execute_tool(
        self, function_call: types.FunctionCall
    ) -> tuple[list[ChatPlaceCard], dict]:
        """
        도구 하나를 실행해 (카드 목록, 모델에 돌려줄 결과)를 반환한다.
        도구가 실패해도 예외를 올리지 않고 error를 모델에 넘겨, 사용자에게
        다시 묻는 식으로 대화를 이어가게 한다.
        """
        args = dict(function_call.args or {})
        try:
            if function_call.name == "search_places":
                cards, tag_matched = await self._handle_search(args)
                extra = {"tag_matched": tag_matched}
            elif function_call.name == "search_tour_places":
                cards = await self._handle_tour_search(args)
                extra = {}
            else:
                return [], {"error": f"지원하지 않는 도구입니다: {function_call.name}"}
        except HTTPException as e:
            return [], {"error": str(e.detail)}
        except Exception:
            logger.exception(f"도구 실행 실패: {function_call.name} {args}")
            return [], {"error": "검색 중 오류가 발생했습니다."}

        payload = {
            "places": [card.model_dump() for card in cards],
            "count": len(cards),
            **extra,
        }
        return cards, payload

    async def _handle_search(
        self, args: dict
    ) -> tuple[list[ChatPlaceCard], bool | None]:
        result, tag_matched = await self.place_service.search_by_region_and_tags(
            region=args["region"],
            category=args["category"],
            tags=args.get("tags") or [],
        )
        return [self._to_card(p) for p in result.places[:5]], tag_matched

    async def _handle_tour_search(self, args: dict) -> list[ChatPlaceCard]:
        region = args["region"]
        result = await self.place_service.search_tour_places(region)
        return [self._to_card(p) for p in result.places[:5]]

    @staticmethod
    def _dedupe(cards: list[ChatPlaceCard]) -> list[ChatPlaceCard]:
        seen: set[str] = set()
        unique = []
        for card in cards:
            if card.place_id not in seen:
                seen.add(card.place_id)
                unique.append(card)
        return unique

    def _to_card(self, p) -> ChatPlaceCard:
        return ChatPlaceCard(
            place_id=p.place_id,
            name=p.name,
            category=p.category,
            address=p.address,
            lat=p.lat,
            lng=p.lng,
            thumbnail_url=p.thumbnail_url,
            tags=p.tags,
        )

    def _extract_function_calls(self, response) -> list[types.FunctionCall]:
        candidates = response.candidates or []
        if not candidates or not candidates[0].content:
            return []
        return [
            part.function_call
            for part in candidates[0].content.parts or []
            if part.function_call
        ]

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
