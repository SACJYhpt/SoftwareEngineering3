"""Keep the existing `uvicorn main:app --reload` entry point."""
import os

from app.api import create_app
from app.site import with_frontend

# Set FRONTEND_DIST to frontend/dist to serve the built site and the API (under /api) together.
app = with_frontend(create_app(), os.getenv("FRONTEND_DIST", ""))
