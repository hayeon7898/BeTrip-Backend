from uuid import uuid4

import pytest

from app.repositories.itinerary_place_repository import ItineraryPlaceRepository


@pytest.mark.asyncio
async def test_get_itinerary_returns_created_itinerary(db_session, sample_itinerary):
    repo = ItineraryPlaceRepository(db_session)

    result = await repo.get_itinerary(sample_itinerary.itinerary_id)

    assert result is not None
    assert result.itinerary_id == sample_itinerary.itinerary_id
    assert result.region == "제주"


@pytest.mark.asyncio
async def test_get_itinerary_returns_none_when_not_found(db_session):
    repo = ItineraryPlaceRepository(db_session)

    result = await repo.get_itinerary(uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_create_and_get_itinerary_place(
    db_session, sample_itinerary, sample_place
):
    repo = ItineraryPlaceRepository(db_session)
    place = sample_place()
    db_session.add(place)
    await db_session.commit()

    created = await repo.create_itinerary_place(
        sample_itinerary.itinerary_id, place.place_id
    )

    assert created.itinerary_place_id is not None
    assert created.day is None
    assert created.time_slot is None
    assert created.order_in_day is None

    found = await repo.get_itinerary_place(created.itinerary_place_id)
    assert found is not None
    assert found.place_id == place.place_id


@pytest.mark.asyncio
async def test_get_existing_place_ids_excludes_already_added(
    db_session, sample_itinerary, sample_place
):
    repo = ItineraryPlaceRepository(db_session)
    place = sample_place()
    db_session.add(place)
    await db_session.commit()

    await repo.create_itinerary_place(sample_itinerary.itinerary_id, place.place_id)

    existing_ids = await repo.get_existing_place_ids(sample_itinerary.itinerary_id)

    assert existing_ids == {place.place_id}


@pytest.mark.asyncio
async def test_get_itinerary_place_by_place_id_detects_duplicate(
    db_session, sample_itinerary, sample_place
):
    repo = ItineraryPlaceRepository(db_session)
    place = sample_place()
    db_session.add(place)
    await db_session.commit()

    await repo.create_itinerary_place(sample_itinerary.itinerary_id, place.place_id)

    found = await repo.get_itinerary_place_by_place_id(
        sample_itinerary.itinerary_id, place.place_id
    )

    assert found is not None


@pytest.mark.asyncio
async def test_get_recommended_places_filters_region_and_excludes_added(
    db_session, sample_itinerary, sample_place
):
    repo = ItineraryPlaceRepository(db_session)

    jeju_place = sample_place(address="제주특별자치도 제주시 A로 1")
    seoul_place = sample_place(address="서울특별시 강남구 B로 2")
    already_added = sample_place(address="제주특별자치도 서귀포시 C로 3")
    db_session.add_all([jeju_place, seoul_place, already_added])
    await db_session.commit()

    await repo.create_itinerary_place(
        sample_itinerary.itinerary_id, already_added.place_id
    )

    results = await repo.get_recommended_places(
        region="제주",
        exclude_place_ids={already_added.place_id},
    )
    result_ids = {p.place_id for p in results}

    assert jeju_place.place_id in result_ids
    assert seoul_place.place_id not in result_ids
    assert already_added.place_id not in result_ids


@pytest.mark.asyncio
async def test_get_recommended_places_filters_by_category(
    db_session, sample_itinerary, sample_place
):
    repo = ItineraryPlaceRepository(db_session)

    cafe = sample_place(category="CAFE", address="제주특별자치도 제주시 A로 1")
    restaurant = sample_place(
        category="RESTAURANT", address="제주특별자치도 제주시 B로 2"
    )
    db_session.add_all([cafe, restaurant])
    await db_session.commit()

    results = await repo.get_recommended_places(
        region="제주", exclude_place_ids=set(), category="CAFE"
    )
    result_ids = {p.place_id for p in results}

    assert cafe.place_id in result_ids
    assert restaurant.place_id not in result_ids


@pytest.mark.asyncio
async def test_delete_itinerary_place(db_session, sample_itinerary, sample_place):
    repo = ItineraryPlaceRepository(db_session)
    place = sample_place()
    db_session.add(place)
    await db_session.commit()

    created = await repo.create_itinerary_place(
        sample_itinerary.itinerary_id, place.place_id
    )

    await repo.delete_itinerary_place(created)

    found = await repo.get_itinerary_place(created.itinerary_place_id)
    assert found is None


@pytest.mark.asyncio
async def test_find_day_places_ordered_uses_chronological_not_alphabetical_order(
    db_session, sample_itinerary, sample_place
):
    """time_slot이 문자열 컬럼이라 알파벳순이면 EVENING < LUNCH < MORNING이 되는데,
    실제로는 MORNING -> LUNCH -> EVENING(하루 시간 순서)으로 나와야 한다."""
    repo = ItineraryPlaceRepository(db_session)
    evening_place = sample_place()
    lunch_place = sample_place()
    morning_place = sample_place()
    db_session.add_all([evening_place, lunch_place, morning_place])
    await db_session.commit()

    # 일부러 알파벳 역순(EVENING, LUNCH, MORNING)으로 생성
    await repo.create_itinerary_place(
        sample_itinerary.itinerary_id,
        evening_place.place_id,
        day=1,
        time_slot="EVENING",
        order_in_day=1,
    )
    await repo.create_itinerary_place(
        sample_itinerary.itinerary_id,
        lunch_place.place_id,
        day=1,
        time_slot="LUNCH",
        order_in_day=1,
    )
    await repo.create_itinerary_place(
        sample_itinerary.itinerary_id,
        morning_place.place_id,
        day=1,
        time_slot="MORNING",
        order_in_day=1,
    )

    ordered = await repo.find_day_places_ordered(sample_itinerary.itinerary_id, 1)
    ordered_place_ids = [place.place_id for _, place in ordered]

    assert ordered_place_ids == [
        morning_place.place_id,
        lunch_place.place_id,
        evening_place.place_id,
    ]


@pytest.mark.asyncio
async def test_find_day_places_ordered_orders_by_order_in_day_within_slot(
    db_session, sample_itinerary, sample_place
):
    repo = ItineraryPlaceRepository(db_session)
    second = sample_place()
    first = sample_place()
    db_session.add_all([second, first])
    await db_session.commit()

    await repo.create_itinerary_place(
        sample_itinerary.itinerary_id,
        second.place_id,
        day=1,
        time_slot="MORNING",
        order_in_day=2,
    )
    await repo.create_itinerary_place(
        sample_itinerary.itinerary_id,
        first.place_id,
        day=1,
        time_slot="MORNING",
        order_in_day=1,
    )

    ordered = await repo.find_day_places_ordered(sample_itinerary.itinerary_id, 1)

    assert [place.place_id for _, place in ordered] == [
        first.place_id,
        second.place_id,
    ]


@pytest.mark.asyncio
async def test_update_travel_times_persists_multiple_rows_in_one_call(
    db_session, sample_itinerary, sample_place
):
    repo = ItineraryPlaceRepository(db_session)
    place_a = sample_place()
    place_b = sample_place()
    db_session.add_all([place_a, place_b])
    await db_session.commit()

    ip_a = await repo.create_itinerary_place(
        sample_itinerary.itinerary_id,
        place_a.place_id,
        day=1,
        time_slot="MORNING",
        order_in_day=1,
    )
    ip_b = await repo.create_itinerary_place(
        sample_itinerary.itinerary_id,
        place_b.place_id,
        day=1,
        time_slot="LUNCH",
        order_in_day=1,
    )

    await repo.update_travel_times([(ip_a, 12), (ip_b, None)])

    refreshed_a = await repo.get_itinerary_place(ip_a.itinerary_place_id)
    refreshed_b = await repo.get_itinerary_place(ip_b.itinerary_place_id)
    assert refreshed_a.travel_time_to_next_min == 12
    assert refreshed_b.travel_time_to_next_min is None
