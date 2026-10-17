import os
from pathlib import Path
from dotenv import load_dotenv

# Charger le fichier .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"

TEMP_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Support des cookies YouTube pour contourner la détection de bot sur VPS/datacenters
COOKIES_FILE = Path(os.getenv("YOUTUBE_COOKIES_PATH", BASE_DIR / "cookies.txt"))

# Si les cookies sont fournis sous forme de variable d'environnement (ex: base64 ou texte direct)
cookies_content_env = os.getenv("YOUTUBE_COOKIES_CONTENT", "").strip()
if cookies_content_env and not COOKIES_FILE.exists():
    try:
        COOKIES_FILE.write_text(cookies_content_env, encoding="utf-8")
    except Exception as e:
        print(f"Avertissement : Impossible d'écrire YOUTUBE_COOKIES_CONTENT dans {COOKIES_FILE}: {e}")

def has_youtube_cookies() -> bool:
    """Vérifie si un fichier de cookies YouTube valide et non-vide est disponible"""
    return COOKIES_FILE.exists() and COOKIES_FILE.stat().st_size > 10

def get_base_ydl_opts() -> dict:
    """Retourne la configuration commune pour yt-dlp (cookies, runtimes JS, anti-blocage)"""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "js_runtimes": {"node": {}},
        "extractor_args": {
            "youtube": {
                "player_client": ["web", "mweb", "android", "ios"]
            }
        }
    }
    if has_youtube_cookies():
        opts["cookiefile"] = str(COOKIES_FILE)
    return opts

