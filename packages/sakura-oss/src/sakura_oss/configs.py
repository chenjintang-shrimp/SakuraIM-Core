from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    oss_debug: bool = False
    oss_database_url: str = Field(default="sqlite+aiosqlite:///./data/oss.db")
    oss_object_root: str = "./data/objects"
    oss_core_verify_url: str = "http://127.0.0.1:21229/internal/oss/verify-token"
    oss_ttl_seconds: int = 86400
    oss_max_size_bytes: int = 33554432
    oss_cleanup_interval_seconds: int = 3600
    oss_listen_host: str = "0.0.0.0"
    oss_listen_port: int = 21230
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
