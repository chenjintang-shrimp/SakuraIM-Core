# 从.env 引入配置
# .env固定在pwd下

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    debug: bool = False
    database_url: str = Field(default="sqlite+aiosqlite:///./data/app.db")
    listen_host: str = "0.0.0.0"
    listen_port: int = 21229
    worker_count: int = 4
    oss_enabled: bool = True
    oss_base_url: str = "http://127.0.0.1:21230"
    oss_ttl_seconds: int = 86400
    oss_max_size_bytes: int = 33554432
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
