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

    # ---- M2 支付（V5.0 五档定价）----
    # 档位 2/3/4：开业礼包 29.9 单次 / AI 合伙人月卡 99 / 创业陪跑年卡 599
    price_single_cents: int = 2990  # 29.9 元 开业礼包（单次）
    price_month_cents: int = 9900  # 99 元/月 AI 合伙人月卡
    price_year_cents: int = 59900  # 599 元/年 创业全程陪跑年卡
    # 档位 5：增值加购包（按项计价，绝不并入标准套餐）
    addon_prices_cents: dict = {
        "poster": 990,  # AI 海报加印 9.9/张
        "video": 4900,  # AI 短视频 49/条
        "avatar": 9900,  # 数字人口播 99/条
        "leads": 19900,  # 供应商深度线索包 199/套
        "logo": 4900,  # AI Logo 与 VI 49 元
    }
    # 年卡赠送额度（体验额度，超出按加购价购买）
    year_gift_video_quota: int = 2  # 2 条 AI 短视频
    year_gift_avatar_quota: int = 1  # 1 条数字人口播
    # 开业礼包附赠工具箱使用权天数
    gift_tool_days: int = 30
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

    # ---- M4-05 / 第7章 AI 成本控制（六道闸门）----
    # 模型路由：默认轻档模型（light），效果不达标才升级 mid/top
    ai_model_tier: str = "light"  # light | mid | top
    # 轮数上限（第7.2）：防智能体放飞
    ai_max_rounds_diagnose: int = 8
    ai_max_rounds_package: int = 25
    ai_max_rounds_coach: int = 10
    # 成本红线（第7.1）：单次/单月 AI 成本上限（分）
    ai_budget_free_cents: int = 5  # 免费诊断 ≤ 0.05 元
    ai_budget_single_cents: int = 350  # 开业礼包 ≤ 3.5 元
    ai_budget_month_cents: int = 1300  # 月卡 ≤ 13 元/月
    ai_budget_year_cents: int = 11000  # 年卡 ≤ 110 元/年
    # 成本占收入比告警阈值（M4-05：超过 25% 自动告警）
    ai_cost_alert_ratio: float = 0.25
    # 模板化交付：10 件交付物中 7 件模板填充 + 3 件 AI 实时生成
    template_deliverable_ratio: float = 0.7

    # ---- M5 裂变（P0）----
    talk_topic_hour: int = 0  # 今日谈资卡每日 0 点自动生成
    share_report_templates: int = 3  # 喜报模板 ≥ 3 种


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
