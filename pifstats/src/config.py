"""
Configuration for PIF Stats extraction system.
Loads environment variables and provides settings for the extraction pipeline.
"""
import os
from pathlib import Path

# Base paths
PIFSTATS_ROOT = Path(__file__).parent.parent
OUTPUTS_DIR = PIFSTATS_ROOT / "outputs"

# Front API Configuration
FRONT_AUTH_TOKEN = os.getenv("FRONT_AUTH_TOKEN")
FRONT_API_BASE_URL = os.getenv("FRONT_API_BASE_URL", "https://api2.frontapp.com")

# OpenAI Configuration (NEVER use gpt-4, always use gpt-4o per CLAUDE.md)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o"

# Extraction settings
MAX_CONVERSATIONS_PER_BATCH = 100
REQUEST_DELAY_SECONDS = 0.5  # Rate limiting delay between API calls

# Output files
FIRMS_OUTPUT_FILE = OUTPUTS_DIR / "firms.json"
CONTACTS_OUTPUT_FILE = OUTPUTS_DIR / "contacts.json"
EXTRACTION_LOG_FILE = OUTPUTS_DIR / "extraction_log.json"

# Ensure outputs directory exists
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
