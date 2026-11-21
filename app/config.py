from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Stock App"
    database_url: str = "sqlite:///./stock.db"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
