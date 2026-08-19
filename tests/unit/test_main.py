import app.core.og_preview_fetcher as og_preview_fetcher_module
from app.main import app, lifespan


async def test_lifespan_closes_og_fetch_client_on_shutdown():
    og_preview_fetcher_module._get_client()

    async with lifespan(app):
        pass

    assert og_preview_fetcher_module._client is None
