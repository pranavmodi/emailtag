"""Synchronous CRUD operations package."""

# Import from the sync.py module (not the package)
import importlib.util
import os
import sys

# Load the sync.py module directly 
sync_file_path = os.path.join(os.path.dirname(__file__), '..', 'sync.py')
spec = importlib.util.spec_from_file_location("sync_module", sync_file_path)
sync_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_module)

# Import the objects from sync.py
email = sync_module.email
tag = sync_module.tag

# Import from this package
from .processing_trace import processing_trace

__all__ = ["email", "tag", "processing_trace"]