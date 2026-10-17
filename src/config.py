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

import shutil

def find_node_binary() -> Optional[str]:
    """Trouve l'exécutable node.js sur le système (PATH standard, /usr/bin, ou CloudPanel nvm)"""
    candidate = shutil.which("node")
    if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    for p in ["/usr/bin/node", "/usr/local/bin/node", "/bin/node"]:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    home = Path.home()
    nvm_nodes = list((home / ".nvm" / "versions" / "node").glob("*/bin/node"))
    if nvm_nodes:
        return str(nvm_nodes[-1])
    return None

def get_base_ydl_opts() -> dict:
    """Retourne la configuration commune pour yt-dlp (cookies, runtimes JS, anti-blocage)"""
    opts = {
        "quiet": True,
        "no_warnings": True,
    }
    node_bin = find_node_binary()
    if node_bin:
        opts["js_runtimes"] = {"node": {"path": node_bin}}
    else:
        opts["js_runtimes"] = {"node": {}}
    if has_youtube_cookies():
        opts["cookiefile"] = str(COOKIES_FILE)
    return opts

import yt_dlp

def run_ydl_with_fallback(ydl_opts: dict, action_fn):
    """
    Exécute une action yt-dlp (extract_info ou download) avec repli intelligent :
    Si l'appel avec cookies échoue avec 'The page needs to be reloaded',
    réessaie automatiquement sans cookies (utile quand YouTube rejette les cookies résidentiels sur IP datacenter).
    """
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return action_fn(ydl)
    except Exception as e:
        err = str(e)
        if "The page needs to be reloaded" in err and "cookiefile" in ydl_opts:
            # Réessayer sans cookiefile
            fallback_opts = {k: v for k, v in ydl_opts.items() if k != "cookiefile"}
            with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                return action_fn(ydl)
        raise


