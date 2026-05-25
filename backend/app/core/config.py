from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Search"
    debug: bool = False
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/aisearch"
    redis_url: str = "redis://localhost:6379/0"
    page_cache_enabled: bool = True

    bot_token: str = ""
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    init_data_max_age_seconds: int = 86400

    # Dev: skip MAX initData HMAC when true (never in production)
    skip_init_data_validation: bool = False

    yandex_folder_id: str = ""
    yandex_api_key: str = ""
    yandex_search_url: str = "https://searchapi.api.cloud.yandex.net/v2/web/search"
    # Model URI suffixes: gpt://{folder_id}/{name}/{version}
    yandex_gpt_lite_model: str = "yandexgpt-lite/latest"
    yandex_gpt_pro_model: str = "yandexgpt/latest"

    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""

    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    cookie_domain: str = ""

    guest_searches_per_day: int = 5
    free_searches_per_day: int = 10
    pro_searches_per_day: int = 200
    global_yandex_requests_per_day: int = 5000

    pro_price_rub: int = 299
    pro_duration_days: int = 30

    admin_api_key: str = ""
    admin_session_expire_hours: int = 12
    admin_bootstrap_email: str = ""
    admin_bootstrap_password: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def yandex_configured(self) -> bool:
        return bool(self.yandex_folder_id and self.yandex_api_key)

    def yandex_model_uri(self, model: str) -> str:
        folder = self.yandex_folder_id
        suffix = self.yandex_gpt_pro_model if model == "pro" else self.yandex_gpt_lite_model
        return f"gpt://{folder}/{suffix}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
