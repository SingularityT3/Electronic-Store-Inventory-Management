"""Environment-based configuration. All values come from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = ""
    cors_origins: str = ""
    # Password given to the sample users by `python -m scripts.seed`.
    seed_user_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
