from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router as v1_router
from app.core.config import settings
from app.core.og_preview_fetcher import aclose_og_fetch_client

OPENAPI_TAGS = [
    {"name": "auth"},
    {"name": "itineraries"},
    {"name": "itinerary_conditions"},
    {"name": "itinerary_places"},
    {"name": "itinerary_plans"},
    {"name": "map"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await aclose_og_fetch_client()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok"}
