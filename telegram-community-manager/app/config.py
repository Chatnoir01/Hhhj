from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_phone: str | None = None
    telegram_bot_token: str | None = None
    target_group: str | None = None
    admin_telegram_id: int | None = None
    dry_run: bool = True
    database_url: str = "sqlite:///data/telegram.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def missing_secrets(self) -> list[str]:
        required = {
            "TELEGRAM_API_ID": self.telegram_api_id,
            "TELEGRAM_API_HASH": self.telegram_api_hash,
            "TELEGRAM_PHONE": self.telegram_phone,
            "TARGET_GROUP": self.target_group,
        }
        return [name for name, value in required.items() if value in (None, "")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
