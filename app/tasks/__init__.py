"""Tasks package."""

from app.tasks.worker import celery_app

# Import task modules to ensure they are registered with Celery
import app.tasks.email
import app.tasks.bill_offer
import app.tasks.pif_extraction
import app.tasks.firm_research
import app.tasks.behavior_analysis
import app.tasks.inbox_audit
