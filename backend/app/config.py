"""Environment-based configuration. All values come from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = ""
    cors_origins: str = ""
    # Session cookies are HTTPS-only; turn off only for plain-HTTP local development.
    cookie_secure: bool = True
    # Password given to the sample users by `python -m scripts.seed`.
    seed_user_password: str = ""

    # Login lockout and session lifetime (SRS A-12).
    lockout_threshold: int = 5
    lockout_minutes: int = 15
    session_idle_minutes: int = 30
    session_max_hours: int = 12

    # Password reset (SEC-AUTH-7): links are emailed and valid for this long.
    password_reset_minutes: int = 30
    # Base URL of the web app, used to build the reset link.
    app_base_url: str = "http://localhost:5173"
    # Outgoing mail. With no host, reset emails are not sent.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    smtp_from: str = "ESIMS <no-reply@esims.local>"


@lru_cache
def get_settings() -> Settings:
    return Settings()
