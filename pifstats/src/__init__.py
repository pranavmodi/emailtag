"""
PIF Stats - Personal Injury Firm Statistics Extraction System

Extract firm and contact information from Front emails.
"""

from .front_client import FrontClient
from .email_parser import EmailParser, ParsedEmail, ExtractedContact
from .entity_extractor import EntityExtractor
from .firm_storage import FirmStorage
from .main import PIFStatsExtractor

__all__ = [
    "FrontClient",
    "EmailParser",
    "ParsedEmail",
    "ExtractedContact",
    "EntityExtractor",
    "FirmStorage",
    "PIFStatsExtractor"
]
