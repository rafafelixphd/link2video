#!/usr/bin/env python3
"""
Batch Segment Processor - Web UI launcher.

Starts Flask server at http://localhost:5000
"""
import sys
import os

import argparse
from app import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Batch Segment Processor")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", default=5123, type=int, help="Port to bind to")
    args = parser.parse_args()

    app = create_app()

    print("=" * 60)
    print("  Batch Segment Processor")
    print(f"  Starting at http://{args.host}:{args.port}")
    print("=" * 60)
    app.run(debug=args.debug, host=args.host, port=args.port)
