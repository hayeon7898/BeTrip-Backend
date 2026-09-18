import re

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.schemas.naver import NaverBlogItem, NaverBlogSearchResult

BLOG_SEARCH_URL = "https://naverapihub.apigw.ntruss.com/search/v1/blog"

_TAG_RE = re.compile(r"</?b>")  # 검색어 강조용 <b> 태그 제거


class NaverBlogClient:
    """
    NAVER API HUB 블로그 검색 클라이언트.
    태그 추출용 스니펫 확보 목적으로만 사용 — 원문 저장 금지,
    LLM 분류 입력으로만 쓰고 버린다.
    """

    def __init__(self):
        self._headers = {
            "X-NCP-APIGW-API-KEY-ID": settings.NAVER_CLIENT_ID,
            "X-NCP-APIGW-API-KEY": settings.NAVER_CLIENT_SECRET,
        }

    async def search_blog(
        self,
        query: str,
        display: int = 10,
        sort: str = "sim",  # sim: 정확도순, date: 최신순
    ) -> NaverBlogSearchResult:
        params = {"query": query, "display": display, "sort": sort}

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(
                    BLOG_SEARCH_URL, params=params, headers=self._headers
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"네이버 블로그 검색 API 오류: {e.response.status_code}",
                ) from e
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="네이버 블로그 검색 API 연결 실패",
                ) from e

            data = resp.json()
            items = [
                NaverBlogItem(
                    title=_TAG_RE.sub("", item["title"]),
                    description=_TAG_RE.sub("", item["description"]),
                    link=item["link"],
                )
                for item in data.get("items", [])
            ]
            return NaverBlogSearchResult(items=items, total=data.get("total", 0))
