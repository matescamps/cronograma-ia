# Entrypoint para Render: uvicorn main:app
# Reexporta a app FastAPI localizada em backend/main.py
from backend.main import app  # noqa: F401
