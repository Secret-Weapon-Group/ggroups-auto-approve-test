import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

GOOGLE_EMAIL = os.getenv("GOOGLE_EMAIL", "")
GOOGLE_PASSWORD = os.getenv("GOOGLE_PASSWORD", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROUP_URL = os.getenv("GROUP_URL", "https://groups.google.com/g/forecast-chat")

# Legacy — used by scraper.py until it is removed
BROWSER_PROFILE_DIR = BASE_DIR / ".browser_profile"
BROWSER_PROFILE_DIR.mkdir(exist_ok=True)

# Email-based moderation settings
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
GROUP_EMAIL = os.getenv("GROUP_EMAIL", "")
