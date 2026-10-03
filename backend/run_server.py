"""
FastAPI Server Launcher for Predictive Maintenance Backend.
"""

import sys
import os
import uvicorn

# Ensure the backend directory is in the sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app

if __name__ == "__main__":
    print("Starting FastAPI Predictive Maintenance server on http://127.0.0.1:8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
