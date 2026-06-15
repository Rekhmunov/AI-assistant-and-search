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
    query_url_index_enabled: bool = True
    query_url_max_bootstrap: int = 4
    query_url_max_per_query: int = 8
    query_url_max_record: int = 5
    query_url_lookup_keys: int = 2

    # Обычный RAG: меньше HTTP, если сниппет уже богатый (см. page_depth.effective_page_fetch_limit)
    page_fetch_max_pages: int = 3
    page_fetch_max_pages_deep: int = 8
    page_fetch_max_concurrent: int = 5
    page_fetch_skip_rich_snippet_chars: int = 1400
    search_parallel_extra_queries: bool = True
    # Follow-ups параллельно с сохранением ответа; после done — короткий wait (см. search_flow)
    follow_ups_deferred: bool = True
    follow_ups_post_done_timeout_sec: float = 4.0

    bot_token: str = ""
    # Shared secret for POST /api/bot/webhook (MAX → our API). Empty = allowed only outside production.
    max_bot_webhook_secret: str = ""
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    # После удаления аккаунта (deleted_at) — срок до окончательного удаления данных из БД
    deleted_account_retention_days: int = 90
    init_data_max_age_seconds: int = 86400

    # Dev: skip MAX initData HMAC when true (never in production)
    skip_init_data_validation: bool = False

    yandex_folder_id: str = ""
    yandex_api_key: str = ""
    yandex_search_url: str = "https://searchapi.api.cloud.yandex.net/v2/web/search"
    yandex_image_search_url: str = "https://searchapi.api.cloud.yandex.net/v2/image/search"
    entity_images_enabled: bool = True
    entity_images_max: int = 5
    entity_images_candidate_limit: int = 14
    entity_images_validate_timeout_sec: float = 4.0
    entity_images_total_timeout_sec: float = 8.0
    # Model URI suffixes: gpt://{folder_id}/{name}/{version}
    yandex_gpt_lite_model: str = "yandexgpt-lite/latest"
    yandex_gpt_pro_model: str = "yandexgpt/latest"
    yandex_alice_vlm_model: str = "aliceai-vlm/latest"
    # Fallback vision в API AI Studio (aliceai-vlm пока нет в каталоге; gemma принимает фото).
    yandex_vision_gemma_model: str = "gemma-3-27b-it"
    # False = gemma первой (пока aliceai-vlm нет в API). True — когда Alice VLM появится в каталоге.
    yandex_vision_alice_first: bool = False
    yandex_vision_image_max_side: int = 1536
    yandex_vision_image_max_bytes: int = 900_000
    # Responses API (vision/multimodal) — не llm.api.../chat/completions.
    yandex_ai_studio_base_url: str = "https://ai.api.cloud.yandex.net/v1"

    anthropic_api_key: str = ""
    # Lite = rewriter/extract; Pro = финальный ответ. ID из console.anthropic.com → Models
    anthropic_model_lite: str = "claude-haiku-4-5-20251001"
    anthropic_model_pro: str = "claude-sonnet-4-6"
    # Если VPS в регионе/сети, где api.anthropic.com отдаёт 403 — HTTP(S) прокси в EU/US
    anthropic_http_proxy: str = ""

    deepseek_api_key: str = ""
    deepseek_model_lite: str = "deepseek-v4-flash"
    deepseek_model_pro: str = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_http_proxy: str = ""

    gigachat_credentials: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_base_url: str = "https://gigachat.devices.sberbank.ru/api/v1"
    gigachat_auth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    gigachat_model_lite: str = "GigaChat-2"
    gigachat_model_pro: str = "GigaChat-2-Pro"
    gigachat_verify_ssl_certs: bool = True
    gigachat_ca_bundle_file: str = ""

    perplexity_api_key: str = ""
    # Sonar API: sonar = Lite (быстрый), sonar-pro = Pro (сложные запросы)
    perplexity_model_lite: str = "sonar"
    perplexity_model_pro: str = "sonar-pro"
    perplexity_base_url: str = "https://api.perplexity.ai"
    perplexity_http_proxy: str = ""
    perplexity_search_recency_filter: str = ""
    perplexity_return_related_questions: bool = True

    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    # Чек 54-ФЗ: 1 = без НДС; tax_system_code — только если задан в кабинете ЮKassa
    yookassa_vat_code: int = 1
    yookassa_tax_system_code: int = 0

    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    cookie_domain: str = ""
    public_web_url: str = "https://glosix.ru"
    api_public_url: str = "https://api.glosix.ru"
    # Deeplink бота MAX (https://max.ru/<bot>) — return_url после оплаты в миниаппе
    max_bot_url: str = ""

    guest_searches_per_day: int = 5
    free_searches_per_day: int = 10
    pro_searches_per_day: int = 200
    free_image_gens_per_day: int = 0
    pro_image_gens_per_day: int = 20
    guest_doc_gens_lifetime: int = 1
    free_doc_gens_per_day: int = 1
    pro_doc_gens_per_day: int = 20
    generated_doc_ttl_hours: int = 72
    upload_ttl_hours: int = 24
    generated_image_ttl_hours: int = 72
    global_yandex_requests_per_day: int = 5000

    pro_price_rub: int = 299
    pro_duration_days: int = 30

    # Временное хранение бинарников фото для vision (TTL = uploaded_files.expires_at)
    upload_storage_dir: str = "/data/uploads"

    admin_api_key: str = ""
    admin_session_expire_hours: int = 12
    admin_bootstrap_email: str = ""

    # SMTP — оповещения администратора о сбоях
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""          # От кого (если пусто — используется smtp_user)
    smtp_use_tls: bool = True    # STARTTLS
    # Куда слать оповещения о сбоях (через запятую)
    alert_emails: str = ""
    admin_bootstrap_password: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def yandex_configured(self) -> bool:
        return bool(self.yandex_folder_id and self.yandex_api_key)

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key.strip())

    @property
    def deepseek_configured(self) -> bool:
        return bool(self.deepseek_api_key.strip())

    @property
    def gigachat_configured(self) -> bool:
        return bool(self.gigachat_credentials.strip())

    @property
    def perplexity_configured(self) -> bool:
        return bool(self.perplexity_api_key.strip())

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host.strip() and self.smtp_user.strip() and self.alert_emails.strip())

    def yandex_model_uri(self, model: str) -> str:
        folder = self.yandex_folder_id
        suffix = self.yandex_gpt_pro_model if model == "pro" else self.yandex_gpt_lite_model
        return f"gpt://{folder}/{suffix}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
