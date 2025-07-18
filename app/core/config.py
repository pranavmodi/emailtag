"""Configuration settings for the application."""

import os
from pathlib import Path
from typing import Any, Dict, Optional, List
import json
import logging

from pydantic import PostgresDsn, field_validator, model_validator, Json, HttpUrl, Field
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
    
    # Service Endpoints
    OCR_API_URL: HttpUrl = "http://localhost:5000/ocr" # Default, override in .env
    MCP_SERVER_URL: HttpUrl = "http://localhost:8001/mcp"

    # FrontApp settings
    FRONT_API_BASE_URL: str = "https://api2.frontapp.com"  # Default Front API base URL
    FRONT_AUTH_TOKEN: str  # Front authentication token
    FRONT_CHANNEL_ID: str  # The ID of the channel to send auto-responses from
    FRONT_APP_WEBHOOK: str  # Front webhook URL for incoming messages
    FRONT_BOT_TEAMMATE_ID: str # ID of the teammate/bot sending replies
    FRONTAPP_WEBHOOK_SECRET: Optional[str] = None # Secret for verifying Front webhook signatures
    FRONT_CHANNEL_PRIMARY_EMAIL: str # The primary email address of your Front channel (for split conversations)

    # Auto-response settings
    DEFAULT_LOCATION: str = "Precise Imaging Center"  # Default location for auto-responses
    CONTACT_NUMBER: str = "(555) 123-4567"  # Default contact number for auto-responses
    BOT_EMAIL_SIGNATURE: Optional[str] = None # Signature to identify bot emails

    # Logging
    LOG_LEVEL: str = "INFO"

    # Topic Splitting Settings
    TOPIC_SPLIT_MESSAGE_HISTORY_COUNT: int = 3 # Number of past messages to consider for topic splitting
    INTERNAL_EMAIL_DOMAINS: List[str] = ["precisemri.com"] # Hardcoded for now

    # Classification Rules
    CLASSIFICATION_RULES_PATH: str = str(ROOT / "app" / "prompts" / "classification_rules.txt")

    # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # OpenAI
    OPENAI_API_KEY: str
    
    # Google API
    GOOGLE_API_KEY: str
    
    # Google Cloud Document AI Settings
    GOOGLE_CLOUD_PROJECT_ID: Optional[str] = "your-google-cloud-project"
    GOOGLE_CLOUD_LOCATION: Optional[str] = "us"
    DOCUMENT_AI_PROCESSOR_ID: Optional[str] = "your-processor-id"
    
    # Roboflow Settings - Pre-trained Strikethrough Detection Model
    ROBOFLOW_API_KEY: Optional[str] = "your-roboflow-api-key"
    ROBOFLOW_MODEL_ID: Optional[str] = "strikethrough-detection/6"
    
    # OpenAI Settings for Vision/Multimodal
    OPENAI_VISION_MODEL: Optional[str] = "gpt-4o"  # Model for image analysis
    OPENAI_MAX_TOKENS: Optional[int] = 1000  # Max tokens for vision responses
    
    # Strikethrough Detection Provider
    STRIKETHROUGH_PROVIDER: Optional[str] = "openai"  # google|roboflow|openai

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

    class Config:
        """Pydantic settings config."""
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env file


# Create settings instance
settings = Settings() 