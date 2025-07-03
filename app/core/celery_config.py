# Add these periodic tasks to your existing CELERYBEAT_SCHEDULE configuration

# OCR Service Monitoring and Recovery Tasks
CELERYBEAT_SCHEDULE_OCR_MONITORING = {
    'check-ocr-service-health': {
        'task': 'tasks.check_ocr_service_health',
        'schedule': 300.0,  # Check every 5 minutes
        'options': {'queue': 'monitoring'}
    },
    'recover-ocr-failed-emails': {
        # Removed – OCR failures now handled inline
    },
}

# Add this to your existing CELERYBEAT_SCHEDULE:
# CELERYBEAT_SCHEDULE.update(CELERYBEAT_SCHEDULE_OCR_MONITORING) 