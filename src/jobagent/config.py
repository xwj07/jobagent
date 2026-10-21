"""Runtime configuration, loaded from environment variables with the JOBAGENT_ prefix."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JOBAGENT_",
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
    )

    # SQLite by default so the repo runs with zero setup; switch to Postgres via env.
    database_url: str = "sqlite:///./jobagent.db"

    # "openai" works with any OpenAI-compatible endpoint (DeepSeek, Qwen, Kimi, ...).
    # "mock" is a deterministic rule-based extractor for offline tests and demos.
    provider: str = "mock"
    llm_base_url: str = "https://ai.gitee.com/v1"
    llm_api_key: str = ""
    llm_model: str = "DeepSeek-V4-Pro-0813"
    audio_model: str = "Qwen3.8-Omni-Flash"
    json_mode: bool = True
    max_retries: int = 3


settings = Settings()
