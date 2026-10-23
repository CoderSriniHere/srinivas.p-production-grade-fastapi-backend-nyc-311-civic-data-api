from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6380/0"
    secret_key: str = "neuleap"
    socrata_api_url: str = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()