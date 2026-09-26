from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_phone: str | None = None
    telegram_bot_token: str | None = None
    target_group: str | None = None
    admin_telegram_id: int | None = None
    admin_api_key: str | None = None

    dry_run: bool = True
    database_url: str = "sqlite:///data/telegram.db"
    session_dir: Path = Path("data/sessions")
    bind_host: str = "127.0.0.1"
    max_upload_bytes: int = 5 * 1024 * 1024
    max_batch_size: int = 100

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("admin_api_key")
    @classmethod
    def validate_admin_api_key(cls, value: str | None) -> str | None:
        if value is not None and len(value) < 32:
            raise ValueError("ADMIN_API_KEY must contain at least 32 characters")
        return value

    def missing_secrets(self) -> list[str]:
        required = {
            "TELEGRAM_API_ID": self.telegram_api_id,
            "TELEGRAM_API_HASH": self.telegram_api_hash,
            "TELEGRAM_PHONE": self.telegram_phone,
            "ADMIN_API_KEY": self.admin_api_key,
        }
        return [name for name, value in required.items() if value in (None, "")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
