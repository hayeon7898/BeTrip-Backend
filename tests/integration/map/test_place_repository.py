from app.repositories.place_repository import PlaceRepository
from tests.integration.map.conftest import create_place


class TestGetByIds:
    async def test_returns_matching_places(self, db_session):
        place1 = await create_place(db_session, place_id="place-1")
        place2 = await create_place(db_session, place_id="place-2")
        await create_place(db_session, place_id="place-3")

        repo = PlaceRepository(db_session)
        result = await repo.get_by_ids(["place-1", "place-2"])

        result_ids = {place.place_id for place in result}
        assert result_ids == {place1.place_id, place2.place_id}

    async def test_ignores_unknown_ids(self, db_session):
        await create_place(db_session, place_id="place-1")

        repo = PlaceRepository(db_session)
        result = await repo.get_by_ids(["place-1", "does-not-exist"])

        assert [place.place_id for place in result] == ["place-1"]

    async def test_returns_empty_list_for_empty_input(self, db_session):
        repo = PlaceRepository(db_session)
        result = await repo.get_by_ids([])

        assert result == []
