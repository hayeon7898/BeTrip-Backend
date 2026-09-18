from datetime import datetime, timedelta

from sqlalchemy import func, select, update
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

    async def find_by_tags(
        self,
        tags: list[str],
        category: str | None = None,
        limit: int = 30,
    ) -> list[Place]:
        """
        태그 containment(@>) 기반 조회.
        예: tags=["감성", "데이트"] -> 두 태그를 모두 가진 장소만 반환.
        idx_places_tags(GIN, jsonb_path_ops) 인덱스를 탄다.
        """
        stmt = select(Place).where(Place.tags.op("@>")(tags))
        if category:
            stmt = stmt.where(Place.category == category)
        stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def set_tags(self, place_id: str, tags: list[str]) -> None:
        """
        네이버 블로그 태그 추출 파이프라인이 사용.
        태그 갱신과 동시에 tags_synced_at을 now()로 찍는다.
        """
        await self.db.execute(
            update(Place)
            .where(Place.place_id == place_id)
            .values(tags=tags, tags_synced_at=func.now())
        )
        await self.db.commit()

    async def find_stale_tags(self, days: int = 90, limit: int = 100) -> list[Place]:
        """
        태그가 없거나(신규 캐시) tags_synced_at이 오래된 장소를 찾아
        비동기 워커가 재수집하도록 한다.
        """
        threshold = datetime.utcnow() - timedelta(days=days)
        stmt = (
            select(Place)
            .where(
                (Place.tags_synced_at.is_(None)) | (Place.tags_synced_at < threshold)
            )
            .limit(limit)
        )
        result = await self.db.execute(stmt)
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
