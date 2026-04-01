import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

DEFAULT_FETCH_DAYS = 2

MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6-20250514",
    "opus": "claude-opus-4-6-20250612",
    "slm": "qwen3-4b"
}
DEFAULT_MODEL = "haiku"


def resolve_model(name: str) -> str:
    """Resolve a short model name (haiku/sonnet/opus) to an API model ID."""
    return MODEL_MAP[name]

GOOGLE_EMAIL = os.getenv("GOOGLE_EMAIL", "")
GOOGLE_PASSWORD = os.getenv("GOOGLE_PASSWORD", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROUP_URL = os.getenv("GROUP_URL", "https://groups.google.com/g/forecast-chat")

# Email-based moderation settings
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
GROUP_EMAIL = os.getenv("GROUP_EMAIL", "")
