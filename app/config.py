from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = ""

    api_prefix: str = "/api/v1"
    api_key: str = ""
    cors_origins: str = "http://localhost:3000"

    # smok95 API (로또 데이터 소스)
    lotto_api_url: str = "https://smok95.github.io/lotto/results"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
