from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SENTINEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Sentinel"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://sentinel:sentinel_dev_password@localhost:5432/sentinel"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    admin_api_key: str | None = None
    rate_limit_fail_open: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
