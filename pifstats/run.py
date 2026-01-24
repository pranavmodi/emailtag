#!/usr/bin/env python3
"""
Run script for PIF Stats module.

Usage:
    emailtag/bin/python pifstats/run.py <conversation_id>
    emailtag/bin/python pifstats/run.py <conversation_id> --json
    emailtag/bin/python pifstats/run.py <conversation_id> --debug
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pifstats.src.main import main

if __name__ == "__main__":
    main()
