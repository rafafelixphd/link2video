"""Pytest configuration — ensure app/ is on sys.path for bare module imports."""
import sys
from pathlib import Path

# factory.py uses bare imports (from job_manager import ...) which require
# the app/ directory to be on sys.path when running tests from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
