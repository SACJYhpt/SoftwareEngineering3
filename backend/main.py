"""Keep the existing `uvicorn main:app --reload` entry point."""
from app.api import create_app

app = create_app()
