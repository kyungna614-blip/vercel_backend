"""
Bootstrap script: uses system python3 but loads all packages from project .venv.
Strips ~/Library/Python from sys.path so the sandbox doesn't hit permission errors.
"""
import sys
import os

# Strip any paths the sandbox blocks (~/Library/Python)
sys.path = [p for p in sys.path if "/Library/Python" not in p]

# Inject project venv site-packages FIRST
_here = os.path.dirname(os.path.abspath(__file__))
_venv_sp = os.path.join(_here, ".venv", "lib", "python3.9", "site-packages")
if os.path.isdir(_venv_sp):
    sys.path.insert(0, _venv_sp)

# Change cwd so relative imports in app work
os.chdir(_here)

import uvicorn

uvicorn.run(
    "app.main:app",
    host="0.0.0.0",
    port=8000,
    loop="asyncio",
    http="h11",
)
