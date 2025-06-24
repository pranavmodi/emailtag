"""
Shared templates used across multiple AI agents.

This module contains response templates that are reused by different agents
to ensure consistent messaging and user experience.
"""

# Template for requesting patient identification (first attempt)
TEMPLATE_REQUEST_PATIENT_ID = "Please provide the patient ID or first name, last name and date of birth."

# Template for escalating to human review after failed patient identification
TEMPLATE_REQUEST_PATIENT_ID_AGAIN_ESCALATE = "Thank you for the information. We're still having trouble locating your appointment details without a Patient ID. A member of our team will personally review your request and get back to you shortly." 