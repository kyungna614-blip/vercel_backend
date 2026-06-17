#!/usr/bin/env python3
"""
Creator Forge Internal Ops — Entry Point
Run: python3 run.py
"""
import os
import sys

# Load .env if present
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"\n{'='*50}")
    print("  CREATOR FORGE — Internal Ops Pipeline")
    print(f"  http://localhost:{port}")
    print(f"  API docs: http://localhost:{port}/docs")
    print(f"{'='*50}\n")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_dirs=["app", "frontend"],
    )
