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
    PROJECT_DESCRIPTION: str = "FastAPI + MongoDB(Beanie) starter"
    PROJECT_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    MONGODB_URL: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection URI.",
    )
    MONGODB_DB: str = Field(
        default="sili",
        description="MongoDB database name.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
