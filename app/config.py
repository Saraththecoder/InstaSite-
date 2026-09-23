import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file if present
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'dukaan_mitra.db'}")
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
STORE_BASE_URL = os.getenv("STORE_BASE_URL", "http://localhost:8000")
PORT = int(os.getenv("PORT", "8000"))

def require_gemini_key() -> str:
    """Fail-fast check for Gemini API key."""
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not set in environment or .env file. "
            "Please obtain an API key from Google AI Studio and set GEMINI_API_KEY."
        )
    return GEMINI_API_KEY

def require_telegram_token() -> str:
    """Fail-fast check for Telegram Bot Token."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN is not set in environment or .env file. "
            "Please create a bot with @BotFather and set TELEGRAM_BOT_TOKEN."
        )
    return TELEGRAM_BOT_TOKEN
