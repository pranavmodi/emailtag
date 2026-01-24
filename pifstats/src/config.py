"""Configuration settings for PIF Stats module."""

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class PifStatsSettings(BaseSettings):
    """Settings for PIF Stats module."""

    # Front API
    FRONT_API_BASE_URL: str = "https://api2.frontapp.com"
    FRONT_AUTH_TOKEN: str

    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o"  # Default model for entity extraction

    # Logging
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    class Config:
        """Pydantic settings config."""
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# Create settings instance
settings = PifStatsSettings()
