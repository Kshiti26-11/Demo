"""Vercel entry point for the SyncSnitch demo site: exposes the FastAPI app as `app`.

Person 4 builds the `webapp` package (WORK.md prompts P4-2 and P4-3).
"""
import sys
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent.parent
if str(WEB_ROOT) not in sys.path:
    sys.path.insert(0, str(WEB_ROOT))

from webapp.main import app  # noqa: E402,F401
