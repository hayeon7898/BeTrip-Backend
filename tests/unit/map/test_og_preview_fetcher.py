from unittest.mock import MagicMock

import httpx
import pytest

import app.core.og_preview_fetcher as og_preview_fetcher_module
from app.core.og_preview_fetcher import (
    aclose_og_fetch_client,
    extract_og_image,
    fetch_og_image,
)


@pytest.fixture(autouse=True)
def _reset_og_fetch_client():
    """모듈 전역 커넥션 풀 싱글턴을 테스트마다 초기화해서 테스트 간 오염을 막는다."""
    og_preview_fetcher_module._client = None
    yield
    og_preview_fetcher_module._client = None


class _FakeStreamResponse:
    def __init__(self, status_code: int, body: bytes):
        self.status_code = status_code
        self._body = body

    async def aiter_bytes(self):
        yield self._body


class _FakeStreamContext:
    def __init__(self, response: _FakeStreamResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def test_fetch_og_image_returns_url_on_success(monkeypatch):
    html = b'<html><head><meta property="og:image" content="https://example.com/a.jpg"></head></html>'
    monkeypatch.setattr(
        httpx.AsyncClient,
        "stream",
        lambda self, method, url: _FakeStreamContext(_FakeStreamResponse(200, html)),
    )

    result = await fetch_og_image("https://place.map.kakao.com/1")

    assert result == "https://example.com/a.jpg"


async def test_fetch_og_image_stops_reading_after_max_bytes(monkeypatch):
    # MAX_BYTES_TO_READ(65536)를 넘는 응답은 <head> 뒷부분까지 다 안 읽고 멈춘다
    big_html = (
        b"x" * 70_000
        + b'<meta property="og:image" content="https://example.com/big.jpg">'
    )

    def fake_stream(self, method, url):
        return _FakeStreamContext(_FakeStreamResponse(200, big_html))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    result = await fetch_og_image("https://place.map.kakao.com/big")

    assert result == "https://example.com/big.jpg"


async def test_fetch_og_image_returns_none_on_non_200(monkeypatch):
    monkeypatch.setattr(
        httpx.AsyncClient,
        "stream",
        lambda self, method, url: _FakeStreamContext(_FakeStreamResponse(404, b"")),
    )

    result = await fetch_og_image("https://place.map.kakao.com/2")

    assert result is None


async def test_fetch_og_image_returns_none_on_request_error(monkeypatch):
    def fake_stream(self, method, url):
        raise httpx.ConnectError("boom", request=MagicMock())

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    result = await fetch_og_image("https://place.map.kakao.com/3")

    assert result is None


async def test_aclose_og_fetch_client_resets_singleton_for_reuse():
    first_client = og_preview_fetcher_module._get_client()

    await aclose_og_fetch_client()
    assert og_preview_fetcher_module._client is None

    second_client = og_preview_fetcher_module._get_client()
    assert second_client is not first_client

    await aclose_og_fetch_client()


def test_extract_og_image_when_present():
    html = '<html><head><meta property="og:image" content="https://example.com/a.jpg"></head></html>'
    assert extract_og_image(html) == "https://example.com/a.jpg"


def test_extract_og_image_when_content_attr_comes_first():
    html = '<meta content="https://example.com/b.jpg" property="og:image">'
    assert extract_og_image(html) == "https://example.com/b.jpg"


def test_extract_og_image_when_missing():
    html = "<html><head><title>no og tag here</title></head></html>"
    assert extract_og_image(html) is None
