#!/bin/bash
cd "/Users/hyejeebae/Downloads/CREATOR FORGE"
exec /Library/Developer/CommandLineTools/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --loop asyncio
