#!/usr/bin/env python3
"""
Batch Segment Processor - Web UI launcher.

Starts Flask server at http://localhost:5000
"""
import sys
import os

# Add project root to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.app import create_app

if __name__ == "__main__":
    app = create_app()
    print("=" * 60)
    print("  Batch Segment Processor")
    print("  Starting at http://localhost:5000")
    print("=" * 60)
    app.run(debug=False, host="127.0.0.1", port=5000)
