import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.naver_client import NaverBlogClient
from app.db.session import AsyncSessionLocal
from app.repositories.place_repository import PlaceRepository
from app.services.tag_service import TagService

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def sync_stale_tags_job(batch_size: int = 20):
    """
    태그가 없거나 오래된 장소를 찾아 네이버 블로그 검색 + LLM 분류로 채운다.
    한 번 실행 시 batch_size개만 처리 — 네이버 API 일일 한도 보호 목적.
    """
    async with AsyncSessionLocal() as db:
        repo = PlaceRepository(db)
        stale_places = await repo.find_stale_tags(days=90, limit=batch_size)

        if not stale_places:
            logger.info("tags sync: 처리할 장소 없음")
            return

        naver_client = NaverBlogClient()
        tag_service = TagService(naver_client, repo)

        success, failed = 0, 0
        for place in stale_places:
            try:
                region = place.address.split()[1] if place.address else ""
                await tag_service.classify_place_tags(
                    place.place_id, place.name, region
                )
                success += 1
            except Exception:
                logger.exception(f"tags sync 실패: place_id={place.place_id}")
                failed += 1

        logger.info(f"tags sync 완료: 성공 {success}, 실패 {failed}")


def start_scheduler():
    scheduler.add_job(
        sync_stale_tags_job,
        trigger="interval",
        minutes=30,  # 확인 끝나면 minutes=30으로 되돌리기
        id="sync_stale_tags",
        replace_existing=True,
    )
    scheduler.start()
    print(f"[SCHEDULER] 시작됨. 등록된 작업: {scheduler.get_jobs()}")  # ← 이 줄 추가
