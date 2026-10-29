from czekachiko.config import Settings

DB = "postgresql+asyncpg://u:p@h/d"


def test_calendar_disabled_without_credentials():
    assert Settings(bot_token="x", database_url=DB, _env_file=None).calendar_enabled is False


def test_calendar_enabled_with_both():
    s = Settings(
        bot_token="x",
        database_url=DB,
        google_service_account_json="/run/secrets/sa.json",
        calendar_id="abc@group.calendar.google.com",
        _env_file=None,
    )
    assert s.calendar_enabled is True
