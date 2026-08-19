import re

import httpx

OG_IMAGE_PATTERN = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
# content가 property보다 먼저 오는 경우도 대응
OG_IMAGE_PATTERN_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.IGNORECASE,
)

# <head> 안에서만 찾으면 되므로 응답을 끝까지 받지 않고 앞부분만 읽는다
MAX_BYTES_TO_READ = 65536

# (1) connect/read를 개별 타임아웃으로 분리
OG_FETCH_TIMEOUT = httpx.Timeout(connect=1.5, read=1.5, write=1.5, pool=1.5)
OG_FETCH_MAX_REDIRECTS = 3

# (2) User-Agent가 없으면 일부 사이트가 봇으로 간주해 차단하거나 응답을 늦출 수 있어
# 일반 브라우저처럼 보이도록 헤더를 붙인다.
OG_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# (3) 요청마다 새 AsyncClient를 만들면 TLS 핸드셰이크를 매번 반복하게 된다.
# 모듈 전역에서 커넥션 풀을 유지하는 client를 만들어 재사용
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=OG_FETCH_TIMEOUT,
            follow_redirects=True,
            max_redirects=OG_FETCH_MAX_REDIRECTS,
            headers=OG_FETCH_HEADERS,
        )
    return _client


async def aclose_og_fetch_client() -> None:
    """앱 종료 시 커넥션 풀을 정리한다. app/main.py의 lifespan에서 호출."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def extract_og_image(html: str) -> str | None:
    """HTML 문자열에서 og:image 메타태그 값만 추출하는 순수 함수 (네트워크 I/O 없음)"""
    match = OG_IMAGE_PATTERN.search(html) or OG_IMAGE_PATTERN_ALT.search(html)
    return match.group(1) if match else None


async def fetch_og_image(url: str) -> str | None:
    """
    주어진 URL의 og:image 메타태그 값만 가볍게 읽어온다.
    페이지 전체를 파싱하지 않고, <head>가 포함될 만큼의 앞부분만 스트리밍으로 읽는다.
    실패해도 예외를 던지지 않고 None을 반환한다 (썸네일은 부가 정보이므로).
    """
    client = _get_client()
    try:
        async with client.stream("GET", url) as resp:
            if resp.status_code != 200:
                return None

            chunks = bytearray()
            async for chunk in resp.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) >= MAX_BYTES_TO_READ:
                    break

            html = chunks.decode("utf-8", errors="ignore")
    except httpx.RequestError:
        return None

    return extract_og_image(html)
