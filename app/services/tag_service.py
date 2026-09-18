from google import genai
from google.genai import types

from app.core.config import settings
from app.core.naver_client import NaverBlogClient
from app.repositories.place_repository import PlaceRepository
from app.schemas.place_tag import PlaceTag, TagClassificationResult

TAG_TAXONOMY = [tag.value for tag in PlaceTag]

SYSTEM_PROMPT = f"""당신은 한국 여행/맛집 블로그 후기에서
장소의 분위기 태그를 추출하는 분류기입니다.

아래는 사용 가능한 태그 목록입니다. 반드시 이 목록에 있는 태그만 사용하세요:
{", ".join(TAG_TAXONOMY)}

규칙:
1. 주어진 블로그 스니펫 중, 실제로 해당 장소를 방문한 후기로 판단되는 것만 참고하세요.
   - 다른 가게의 위치 설명을 위해 장소명이 언급된 경우("OO 건너편에 있는")는 무시하세요.
   - 스쳐 지나가듯 언급만 된 경우("근처 스타벅스에서 커피 마시고")도 무시하세요.
2. 목록에 없는 새 태그를 만들지 마세요.
3. 근거가 부족하면 빈 배열을 반환하세요. 추측해서 채우지 마세요.
"""


class TagService:
    def __init__(self, naver_client: NaverBlogClient, repo: PlaceRepository):
        self.naver_client = naver_client
        self.repo = repo
        self.llm = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def classify_place_tags(
        self, place_id: str, place_name: str, region: str
    ) -> list[str]:
        search_result = await self.naver_client.search_blog(
            f"{place_name} {region} 후기", display=8
        )
        if not search_result.items:
            await self.repo.set_tags(place_id, [])
            return []

        snippets = "\n---\n".join(
            f"[{i + 1}] {item.title}\n{item.description}"
            for i, item in enumerate(search_result.items)
        )
        user_prompt = f"장소명: {place_name}\n\n블로그 스니펫:\n{snippets}"

        response = await self.llm.aio.models.generate_content(
            model="gemini-3.6-flash",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=TagClassificationResult,
            ),
        )

        result: TagClassificationResult = response.parsed
        tags = [tag.value for tag in result.tags]

        await self.repo.set_tags(place_id, tags)
        return tags
