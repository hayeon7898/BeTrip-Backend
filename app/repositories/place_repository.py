from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.place import Place


class PlaceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, place_id: str) -> Place | None:
        result = await self.db.execute(select(Place).where(Place.place_id == place_id))
        return result.scalar_one_or_none()

    async def get_by_ids(self, place_ids: list[str]) -> list[Place]:
        """검색 결과 중 이미 캐시된 place만 골라내기 위한 배치 조회 (캐시 스킵용)."""
        if not place_ids:
            return []
        result = await self.db.execute(
            select(Place).where(Place.place_id.in_(place_ids))
        )
        return list(result.scalars().all())

    async def upsert_many(self, rows: list[dict]) -> None:
        """
        검색 결과를 places 테이블에 배치로 upsert한다.
        place_id(PK) 충돌 시 최신 카카오 데이터로 덮어쓰되, created_at은 보존한다.
        """
        if not rows:
            return

        stmt = pg_insert(Place).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Place.place_id],
            set_={
                "name": stmt.excluded.name,
                "category": stmt.excluded.category,
                "address": stmt.excluded.address,
                "lat": stmt.excluded.lat,
                "lng": stmt.excluded.lng,
                "place_url": stmt.excluded.place_url,
                "thumbnail_url": stmt.excluded.thumbnail_url,
                "source_synced_at": func.now(),
            },
        )
        await self.db.execute(stmt)
        await self.db.commit()
