"""Tasks package."""

from app.tasks.worker import celery_app

# Import task modules to ensure they are registered with Celery
import app.tasks.email
import app.tasks.pif_extraction 