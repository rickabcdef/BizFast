"""应用配置（pydantic-settings 读取 .env）。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret_key: str = "change-me-please"

    database_url: str = "postgresql+asyncpg://bizfast:bizfast@localhost:5432/bizfast"

    # 缓存 / 队列：REDIS_URL 为空时自动降级为「进程内内存缓存 + 进程内异步任务」
    # （本地无 Docker 也能把网页版全链路跑通；生产保持 Redis/RQ 不变）
    redis_url: str = "redis://localhost:6379/0"
    rq_queue: str = "default"
    queue_backend: str = "auto"  # auto | rq | inline

    # 对象存储：s3（MinIO/云 OSS） | local（本地磁盘，便于本地调试）
    storage_backend: str = "auto"  # auto | s3 | local
    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket: str = "bizfast"
    storage_public_base: str = "http://localhost:9000/bizfast"
    local_storage_dir: str = "var/storage"
    # 本地存储对外访问前缀（由 app.routers.files 提供下载）
    local_storage_base_url: str = "/api/files"

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

    # ---- M2 诊断 ----
    diagnose_cache_ttl_seconds: int = 24 * 3600  # M2-06：诊断结果缓存 24h
    # 单个诊断阶段的最低展示时长（纯 UX 节奏参数；进度百分比严格等于真实完成阶段数，不造假）
    diagnose_stage_min_ms: int = 450
    diagnose_mock_ai: bool = False  # 强制走本地规则引擎（无大模型 Key 时的备用路径）
    heatmap_width: int = 1080
    heatmap_height: int = 1440

    # ---- M3 商机 ----
    free_opportunity_count: int = 3  # M3-01：免费展示 3 个
    opportunity_cache_ttl_seconds: int = 24 * 3600

    # ---- M5 支付 ----
    price_single_cents: int = 990  # 9.9 元
    price_month_cents: int = 3900  # 39 元
    price_year_cents: int = 19900  # 199 元
    order_expire_minutes: int = 30  # 待支付超时关闭
    refund_window_days: int = 7  # M5-07：7 天无理由
    payment_mock: bool = True  # 未接真实渠道时走本地模拟支付（回调可自行触发）
    city_list_version: str = "2026.10"
    # M2-05 分享：二维码指向的正式落地页域名（留空则用当前请求的 host，方便本地联调）
    share_base_url: str = ""
    # M5-08 自动续费：到期前多少天提醒
    renew_notice_days: int = 3

    # ---- M9 消息 ----
    notify_dnd_default_start: str = "22:00"
    notify_dnd_default_end: str = "08:00"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def resolved_queue_backend() -> str:
    """解析实际使用的队列后端。"""
    if settings.queue_backend in ("rq", "inline"):
        return settings.queue_backend
    return "rq" if settings.redis_url else "inline"


def resolved_storage_backend() -> str:
    """解析实际使用的存储后端。"""
    if settings.storage_backend in ("s3", "local"):
        return settings.storage_backend
    return "s3" if settings.storage_endpoint else "local"
