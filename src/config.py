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

from typing import Optional, Dict, Any
import shutil

def find_js_runtime() -> Dict[str, Any]:
    """Trouve un runtime JS compatible (node ou deno) pour le solveur de challenges yt-dlp EJS"""
    # 1. Tester node
    node_candidate = shutil.which("node")
    if node_candidate and os.path.isfile(node_candidate) and os.access(node_candidate, os.X_OK):
        return {"node": {"path": node_candidate}}

    home = Path.home()
    for p in [
        home / ".local" / "bin" / "node",
        Path("/usr/bin/node"),
        Path("/usr/local/bin/node"),
        Path("/bin/node"),
    ]:
        if p.is_file() and os.access(p, os.X_OK):
            return {"node": {"path": str(p)}}

    nvm_nodes = list((home / ".nvm" / "versions" / "node").glob("*/bin/node"))
    if nvm_nodes:
        return {"node": {"path": str(nvm_nodes[-1])}}

    # 2. Tester deno
    deno_candidate = shutil.which("deno")
    if deno_candidate and os.path.isfile(deno_candidate) and os.access(deno_candidate, os.X_OK):
        return {"deno": {"path": deno_candidate}}

    for p in [
        home / ".deno" / "bin" / "deno",
        home / ".local" / "bin" / "deno",
        Path("/usr/bin/deno"),
        Path("/usr/local/bin/deno"),
    ]:
        if p.is_file() and os.access(p, os.X_OK):
            return {"deno": {"path": str(p)}}

    return {}

def find_ffmpeg_location() -> Optional[str]:
    """Trouve le dossier contenant ffmpeg sur le système"""
    cand = shutil.which("ffmpeg")
    if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
        return str(Path(cand).parent)
    home = Path.home()
    local_bin = home / ".local" / "bin" / "ffmpeg"
    if local_bin.is_file() and os.access(local_bin, os.X_OK):
        return str(local_bin.parent)
    for p in ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/bin/ffmpeg"]:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return str(Path(p).parent)
    return None

def get_base_ydl_opts() -> dict:
    """Retourne la configuration commune pour yt-dlp (cookies, runtimes JS, anti-blocage)"""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["default", "-tv_downgraded"]
            }
        }
    }
    js_runtimes = find_js_runtime()
    if js_runtimes:
        opts["js_runtimes"] = js_runtimes

    ffmpeg_dir = find_ffmpeg_location()
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir

    if has_youtube_cookies():
        opts["cookiefile"] = str(COOKIES_FILE)
    return opts

import yt_dlp

def run_ydl_with_fallback(ydl_opts: dict, action_fn):
    """
    Exécute une action yt-dlp (extract_info ou download) avec repli intelligent :
    Si l'appel avec cookies échoue avec 'The page needs to be reloaded',
    réessaie sans cookies. Si le repli échoue également (ex: détection bot datacenter),
    conserve l'erreur d'origine pour diagnostic précis.
    """
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return action_fn(ydl)
    except Exception as e:
        err = str(e)
        if "The page needs to be reloaded" in err and "cookiefile" in ydl_opts:
            # Réessayer sans cookiefile
            try:
                fallback_opts = {k: v for k, v in ydl_opts.items() if k != "cookiefile"}
                with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                    return action_fn(ydl)
            except Exception:
                raise e
        raise



