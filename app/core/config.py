from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "BeTrip"
    APP_VERSION: str = "0.1.0"

    DATABASE_URL: str
    OPENAI_API_KEY: str

    # --- Auth ---
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # --- API ---
    API_V1_PREFIX: str = "/api/v1"

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5173"

    # --- KAKAO ---
    KAKAO_REST_API_KEY: str

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()
        ]


settings = Settings()
