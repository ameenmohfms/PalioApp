"""12-factor settings. APP_ENV unset => production (fail-safe, D12)."""

from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    development = "development"
    test = "test"
    production = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: AppEnv = AppEnv.production
    data_region: str = "unset"

    database_url: str = "postgresql+psycopg://palio:palio-dev-only@localhost:5432/palio"

    anthropic_api_key: str = ""
    palio_model_fast: str = "claude-haiku-4-5"
    palio_model_main: str = "claude-sonnet-5"

    palio_daily_token_budget_per_user: int = 200_000

    # Paths to operator-controlled assets (mounted read-only in Docker).
    config_dir: str = "/config"
    prompts_dir: str = "/prompts"
    content_dir: str = "/content"

    # N8 escape hatch for development only; refused in production (see safety.crisis_config).
    allow_unverified_crisis_config: bool = False

    # Per-agent kill-switches (spec §5): 1 = agent disabled.
    palio_kill_companion: bool = False
    palio_kill_assessment: bool = False
    palio_kill_psychoeducation: bool = False
    palio_kill_coach: bool = False
    palio_kill_pattern_extractor: bool = False
    palio_kill_case_review: bool = False
    palio_kill_reports: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env == AppEnv.production


@lru_cache
def get_settings() -> Settings:
    return Settings()
