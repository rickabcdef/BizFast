"""应用配置（pydantic-settings 读取 .env）。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret_key: str = "change-me-please"

    database_url: str = "postgresql+asyncpg://bizfast:bizfast@localhost:5432/bizfast"

    redis_url: str = "redis://localhost:6379/0"
    rq_queue: str = "default"

    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket: str = "bizfast"
    storage_public_base: str = "http://localhost:9000/bizfast"

    ai_primary_base: str = ""
    ai_primary_key: str = ""
    ai_primary_model: str = ""
    ai_backup_base: str = ""
    ai_backup_key: str = ""
    ai_backup_model: str = ""

    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    refresh_token_expire_days: int = 30

    # 合规：不存储用户输入原文
    retention_keep_user_input: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
