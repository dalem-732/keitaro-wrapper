"""Настройки приложения (читаются из окружения и файла .env)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Keitaro Admin API
    keitaro_api_url: HttpUrl = Field(
        default=HttpUrl("https://keitaro-for-tests.etolegko.com/admin_api/v1")
    )
    keitaro_api_key: SecretStr = SecretStr("")
    keitaro_timeout_seconds: float = 10.0
    keitaro_max_retries: int = 3
    keitaro_retry_backoff_seconds: float = 0.5
    # Ссылка на админку для кнопки VIEW IN KT. Если пусто — выводится из keitaro_api_url.
    keitaro_admin_url: str = ""

    # База данных. По умолчанию — локальный SQLite, в docker-compose — PostgreSQL.
    database_url: str = f"sqlite+aiosqlite:///{ROOT_DIR / 'keitaro_wrapper.db'}"

    # Создаватор: префикс имён кампаний и значения по умолчанию для настроек кампании.
    campaign_name_prefix: str = "test_lebedev_"
    # Защита от случайной записи в чужие кампании общего аккаунта:
    # редактор публикует изменения только в кампании с этим префиксом. Пусто — без ограничений.
    write_allowed_prefix: str = "test_lebedev_"
    default_domain: str = ""  # имя или id; пусто — первый доступный домен
    default_group: str = "FORTESTS"
    default_traffic_source: str = "FORTESTS"
    geo_redirect_url: str = "https://google.com"

    offers_cache_ttl_seconds: int = 300
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    frontend_dist: Path = ROOT_DIR / "frontend" / "dist"

    @field_validator("campaign_name_prefix", "write_allowed_prefix")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @property
    def api_base_url(self) -> str:
        return str(self.keitaro_api_url).rstrip("/")

    @property
    def admin_base_url(self) -> str:
        if self.keitaro_admin_url:
            return self.keitaro_admin_url.rstrip("/")
        base = self.api_base_url
        marker = "/admin_api"
        if marker in base:
            return base.split(marker, 1)[0] + "/admin"
        return base


@lru_cache
def get_settings() -> Settings:
    return Settings()
