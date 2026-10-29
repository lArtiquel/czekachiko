from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: SecretStr
    database_url: str
    admin_tg_id: int | None = None
    google_service_account_json: str | None = None
    calendar_id: str | None = None
    calendar_public_url: str | None = None

    @property
    def calendar_enabled(self) -> bool:
        return bool(self.google_service_account_json and self.calendar_id)
