from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from google.genai import types

from app.schemas.place import PlaceSearchResponse, PlaceSearchResult
from app.services.conversation_service import ConversationService


def _response(parts: list[types.Part]) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts))]
    )


def _call(name: str, **args) -> types.Part:
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


def _text(text: str) -> types.GenerateContentResponse:
    return _response([types.Part.from_text(text=text)])


def _place(place_id: str, category: str = "RESTAURANT") -> PlaceSearchResult:
    return PlaceSearchResult(
        place_id=place_id,
        name=f"장소-{place_id}",
        category=category,
        address="경북 경주시",
        lat=35.83,
        lng=129.21,
        thumbnail_url=None,
    )


@pytest.fixture
def place_service():
    return AsyncMock()


@pytest.fixture
def chat_session():
    return MagicMock(send_message=AsyncMock())


@pytest.fixture
def service(place_service, chat_session):
    conversation_repo = AsyncMock()
    conversation_repo.get_history.return_value = []
    svc = ConversationService(conversation_repo, place_service)
    svc.llm = MagicMock()
    svc.llm.aio.chats.create.return_value = chat_session
    return svc


def _sent_function_responses(chat_session, call_index: int = 1) -> list:
    parts = chat_session.send_message.await_args_list[call_index].args[0]
    return [part.function_response for part in parts]


async def test_executes_every_function_call_in_one_response(
    service, place_service, chat_session
):
    """'관광지랑 맛집 둘 다' 처럼 도구 2개를 부르면 둘 다 실행해 결과를 합친다."""
    chat_session.send_message.side_effect = [
        _response(
            [
                _call("search_tour_places", region="경주"),
                _call("search_places", region="경주", category="RESTAURANT"),
            ]
        ),
        _text("경주 관광지와 맛집을 찾아봤어요."),
    ]
    place_service.search_tour_places.return_value = PlaceSearchResponse(
        places=[_place("tour_1", "ACTIVITY")], has_next=False
    )
    place_service.search_by_region_and_tags.return_value = (
        PlaceSearchResponse(places=[_place("k1")], has_next=False),
        None,
    )

    result = await service.send_message("it-1", "경주 관광지랑 맛집 둘 다 알려줘")

    place_service.search_tour_places.assert_awaited_once_with("경주")
    place_service.search_by_region_and_tags.assert_awaited_once()
    responses = _sent_function_responses(chat_session)
    assert [r.name for r in responses] == ["search_tour_places", "search_places"]
    assert {p.place_id for p in result.places} == {"tour_1", "k1"}


async def test_tool_error_is_sent_back_to_model_instead_of_raising(
    service, place_service, chat_session
):
    chat_session.send_message.side_effect = [
        _response([_call("search_places", region="홍데", category="CAFE")]),
        _text("'홍데'라는 지역을 찾지 못했어요. 홍대를 말씀하신 걸까요?"),
    ]
    place_service.search_by_region_and_tags.side_effect = HTTPException(
        status_code=404, detail="'홍데'에 해당하는 위치를 찾을 수 없습니다"
    )

    result = await service.send_message("it-1", "홍데 카페")

    [response] = _sent_function_responses(chat_session)
    assert "error" in response.response
    assert result.places == []
    assert "홍대" in result.reply


async def test_tag_matched_flag_is_passed_to_model(
    service, place_service, chat_session
):
    chat_session.send_message.side_effect = [
        _response(
            [_call("search_places", region="성수", category="CAFE", tags=["루프탑"])]
        ),
        _text("루프탑 카페는 못 찾아서 성수 카페를 보여드릴게요."),
    ]
    place_service.search_by_region_and_tags.return_value = (
        PlaceSearchResponse(places=[_place("k1", "CAFE")], has_next=False),
        False,
    )

    await service.send_message("it-1", "성수 루프탑 카페")

    [response] = _sent_function_responses(chat_session)
    assert response.response["tag_matched"] is False


async def test_duplicate_places_across_calls_are_merged(
    service, place_service, chat_session
):
    chat_session.send_message.side_effect = [
        _response([_call("search_places", region="홍대", category="CAFE")]),
        _response([_call("search_places", region="홍대", category="CAFE")]),
        _text("홍대 카페예요."),
    ]
    place_service.search_by_region_and_tags.return_value = (
        PlaceSearchResponse(places=[_place("k1", "CAFE")], has_next=False),
        None,
    )

    result = await service.send_message("it-1", "홍대 카페")

    assert [p.place_id for p in result.places] == ["k1"]


async def test_replies_directly_when_no_tool_is_called(
    service, place_service, chat_session
):
    chat_session.send_message.side_effect = [_text("어느 지역에서 찾으시나요?")]

    result = await service.send_message("it-1", "카페 추천해줘")

    assert chat_session.send_message.await_count == 1
    place_service.search_by_region_and_tags.assert_not_awaited()
    assert result.reply == "어느 지역에서 찾으시나요?"
