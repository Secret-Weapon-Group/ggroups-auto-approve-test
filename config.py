import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

GOOGLE_EMAIL = os.getenv("GOOGLE_EMAIL", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROUP_URL = os.getenv("GROUP_URL", "https://groups.google.com/g/forecast-chat")

BROWSER_PROFILE_DIR = BASE_DIR / ".browser_profile"
BROWSER_PROFILE_DIR.mkdir(exist_ok=True)
