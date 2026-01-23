#!/usr/bin/env python
"""
Convenience script to run PIF Stats extraction.
Run from the emailtag project root using: emailtag/bin/python pifstats/run.py
"""
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Load environment variables from .env if available
from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

import asyncio
from pifstats.src.main import main

if __name__ == "__main__":
    asyncio.run(main())
