"""Configuration settings for the application."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings

# Project directory
ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings."""

    # API
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "EmailTag"
    VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: PostgresDsn
    ASYNC_DATABASE_URL: Optional[PostgresDsn] = None

    @field_validator("ASYNC_DATABASE_URL", mode="before")
    def assemble_async_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        """Assemble async database connection string if not provided."""
        if v:
            return v

        if not values.get("DATABASE_URL"):
            return None

        db_url = values["DATABASE_URL"]
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=db_url.username,
            password=db_url.password,
            host=db_url.host,
            port=db_url.port,
            path=db_url.path,
        )

    # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # OpenAI
    OPENAI_API_KEY: str

    # FrontApp
    FRONTAPP_API_KEY: str
    FRONTAPP_WEBHOOK_SECRET: str

    # Logging
    LOG_LEVEL: str = "INFO"

    class Config:
        """Pydantic settings config."""
        env_file = ".env"
        case_sensitive = True


# Create settings instance
settings = Settings() 