"""
Vercel Python entrypoint — imports the FastAPI app for serverless deployment.
Vercel looks for `app` or `handler` in api/index.py
"""
import sys
from pathlib import Path

# Ensure project root is on the path so `app.*` imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: F401

# Vercel also accepts `handler`
handler = app
