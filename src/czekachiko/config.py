from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_WEBAPP_URL = "https://lartiquel.github.io/czekachiko/"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    bot_token: SecretStr
    database_url: str
    admin_tg_id: int | None = None
    google_service_account_json: str | None = None
    calendar_id: str | None = None
    calendar_public_url: str | None = None
    webapp_url: str = DEFAULT_WEBAPP_URL
    # Daily import of the pobyt-tracker dataset at 04:00 Europe/Warsaw (bot process only).
    pobytrack_import: bool = True

    @property
    def calendar_enabled(self) -> bool:
        return bool(self.google_service_account_json and self.calendar_id)
