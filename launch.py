#!/usr/bin/env python3
"""Batch Processor — web UI launcher."""
import argparse

from app.factory import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Batch Segment Processor")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", default=5123, type=int, help="Port to bind to")
    parser.add_argument("--jobs-dir", default="app/.jobs", help="Directory for job JSON files")
    args = parser.parse_args()

    app = create_app(jobs_dir=args.jobs_dir)

    display_host = "localhost" if args.host == "0.0.0.0" else args.host
    print("=" * 60)
    print("  Batch Segment Processor")
    print(f"  http://{display_host}:{args.port}")
    print("=" * 60)

    app.run(debug=args.debug, host=args.host, port=args.port)
