"""Test environment defaults for import-time settings validation."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/emailtag_test")
os.environ.setdefault("ASYNC_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/emailtag_test")
os.environ.setdefault("EMAIL_CATEGORIES", "{}")
os.environ.setdefault("TAG_TO_INBOX_MAPPING", "{}")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("FRONT_AUTH_TOKEN", "test-front-token")
os.environ.setdefault("FRONT_CHANNEL_ID", "cha_test")
os.environ.setdefault("FRONT_APP_WEBHOOK", "https://example.test/webhook")
os.environ.setdefault("FRONT_BOT_TEAMMATE_ID", "tea_test")
os.environ.setdefault("FRONT_CHANNEL_PRIMARY_EMAIL", "front@example.test")
os.environ.setdefault("GOOGLE_API_KEY", "test-google-key")
os.environ.setdefault("RADFLOW_UPLOAD_ENDPOINT", "https://example.test/upload")
os.environ.setdefault("PIFSTATS_AUTH_TOKEN", "test-pifstats-token")
os.environ.setdefault("FORCE_HTTPS", "false")
