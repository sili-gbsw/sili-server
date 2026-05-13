from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "Sili Server"
    PROJECT_DESCRIPTION: str = "FastAPI + SQLAlchemy(Async) starter"
    PROJECT_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./sili.db",
        description="SQLAlchemy async DSN. Examples: "
        "sqlite+aiosqlite:///./sili.db, "
        "postgresql+asyncpg://user:pass@host:5432/db",
    )
    DB_ECHO: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
