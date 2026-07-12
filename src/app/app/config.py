from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/chronographer"
    api_key: str = Field(default="change-me", min_length=1)
    default_timezone: str = "America/Los_Angeles"
    user_display_name: str = "Chronographer User"
    occurrence_limit: int = 500

    @property
    def sqlalchemy_database_url(self) -> str:
        value = self.database_url
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
