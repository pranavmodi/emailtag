"""Configuration settings for the application."""

import os
from pathlib import Path
from typing import Any, Dict, Optional, HttpUrl
import json

from pydantic import PostgresDsn, field_validator, model_validator, Json
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

    # SSL/TLS Settings
    SSL_ENABLED: bool = True
    SSL_CERT_FILE: Optional[str] = None
    SSL_KEY_FILE: Optional[str] = None
    FORCE_HTTPS: bool = True

    # Server Settings
    PORT: int = 8000  # Default to 8000 if not set in .env

    # Database
    DATABASE_URL: PostgresDsn
    ASYNC_DATABASE_URL: Optional[PostgresDsn] = None
    
    # PostgreSQL specific settings
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_SERVER: Optional[str] = None
    POSTGRES_PORT: Optional[str] = None
    POSTGRES_DB: Optional[str] = None
    
    # Email Classification Categories
    EMAIL_CATEGORIES: Json[Dict[str, Any]]

    # Model settings
    LLM_PROVIDER: Optional[str] = None
    OPENAI_MODEL_VERSION: Optional[str] = None
    AGENT_MODEL: Optional[str] = None

    # New settings
    MAX_CLASSIFICATION_RETRIES: int = 3
    FRONTAPP_API_TOKEN: str
    FRONTAPP_WEBHOOK_SECRET: str
    
    # Add OCR Service Endpoint
    OCR_SERVICE_ENDPOINT: HttpUrl = "http://localhost:5000/ocr" # Default, override in .env

    @field_validator("ASYNC_DATABASE_URL", mode="before")
    def assemble_async_db_connection(cls, v: Optional[str], info) -> Any:
        """Assemble async database connection string if not provided."""
        if v:
            return v

        # In Pydantic v2, the 'values' parameter is now a ValidationInfo object
        # We need to access the data dictionary differently
        data = info.data
        
        if "DATABASE_URL" not in data or not data["DATABASE_URL"]:
            return None

        db_url = data["DATABASE_URL"]
        # Convert to string and parse components manually instead of accessing attributes
        db_url_str = str(db_url)
        
        # Parse the URL components
        # Format is typically: postgresql://username:password@host:port/dbname
        # Remove the scheme part (postgresql://)
        url_without_scheme = db_url_str.split("://", 1)[1]
        
        # Split auth info from the rest
        if "@" in url_without_scheme:
            auth, rest = url_without_scheme.split("@", 1)
        else:
            auth = ""
            rest = url_without_scheme
            
        # Parse username and password
        username = password = ""
        if auth:
            if ":" in auth:
                username, password = auth.split(":", 1)
            else:
                username = auth
                
        # Parse host, port, and database path
        host_port, path = rest.split("/", 1) if "/" in rest else (rest, "")
        
        # Parse host and port
        if ":" in host_port:
            host, port = host_port.split(":", 1)
        else:
            host = host_port
            port = "5432"  # Default PostgreSQL port
            
        # Build the async URL
        return f"postgresql+asyncpg://{username}{':' + password if password else ''}@{host}:{port}/{path}"

    # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # OpenAI
    OPENAI_API_KEY: str

    # Classification Rules
    CLASSIFICATION_RULES_PATH: str = str(ROOT / "app" / "prompts" / "classification_rules.txt")

    # FrontApp
    FRONT_AUTH_TOKEN: str # Use Bearer token for API calls
    FRONT_API_BASE_URL: str = "https://api2.frontapp.com" # Default Front API base URL

    # Logging
    LOG_LEVEL: str = "INFO"

    class Config:
        """Pydantic settings config."""
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env file


# Create settings instance
settings = Settings() 