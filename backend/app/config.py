"""Central configuration loaded from backend/.env.

Why: one place to read environment settings so the rest of the code never
touches os.environ directly (easier to test and to explain).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

PLACEHOLDER_KEY = "your_groq_api_key_here"


class Settings:
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
    # Speech-to-text for voice input (Groq-hosted Whisper; same API key).
    GROQ_WHISPER_MODEL: str = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo").strip()
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/aivoa_qms"
    ).strip()
    DEFAULT_SITE: str = os.getenv("DEFAULT_SITE", "Main API Plant").strip()
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "").strip()
    POPPLER_PATH: str = os.getenv("POPPLER_PATH", "").strip()
    # Comma-separated list of browser origins allowed to call the API (e.g. a hosted frontend URL).
    # In Docker the frontend proxies /api on the same origin, so the default is enough.
    CORS_ORIGINS: list[str] = [o.strip() for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080").split(",") if o.strip()]

    @property
    def mock_mode(self) -> bool:
        """No usable Groq key -> run the offline rule-based parser so the app still works."""
        return not self.GROQ_API_KEY or self.GROQ_API_KEY == PLACEHOLDER_KEY


settings = Settings()
