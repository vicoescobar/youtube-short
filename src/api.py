import os
import json
import uuid
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import OUTPUT_DIR, TEMP_DIR, GEMINI_API_KEY, COOKIES_FILE, has_youtube_cookies, get_base_ydl_opts, run_ydl_with_fallback, find_js_runtime
from src.extractor import get_video_metadata, extract_transcript, format_timestamp, sanitize_youtube_url
from src.analyzer import analyze_video_for_viral_clips
from src.clipper import (
    generate_ass_subtitles,
    download_video_segment,
    render_vertical_short,
)
import yt_dlp

app = FastAPI(title="YouTube Shorts Viral Clipper API", version="1.0.0")

# Autoriser les requêtes CORS en développement
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stockage en mémoire de l'état des jobs
jobs: Dict[str, Dict[str, Any]] = {}

class AnalyzeRequest(BaseModel):
    url: str
    crop_mode: str = "crop" # "crop" ou "blur"
    auto_render: bool = True

class CookiesPayload(BaseModel):
    content: str

class CookieTestRequest(BaseModel):
    url: Optional[str] = None


def run_pipeline_task(job_id: str, url: str, crop_mode: str, auto_render: bool):
    """Tâche d'arrière-plan exécutant l'extraction, l'analyse et le rendu optionnel"""
    job = jobs[job_id]
    try:
        clean_url = sanitize_youtube_url(url)
        job["status"] = "processing"
        job["step"] = "Récupération des métadonnées de la vidéo..."
        job["updated_at"] = datetime.now().isoformat()

        metadata = get_video_metadata(clean_url)
        job["metadata"] = {
            "title": metadata.title,
            "channel": metadata.channel,
            "duration": metadata.duration,
            "video_id": metadata.video_id,
            "webpage_url": metadata.webpage_url,
        }

        job["step"] = "Extraction et transcription de la vidéo..."
        job["updated_at"] = datetime.now().isoformat()
        segments = extract_transcript(clean_url, metadata)
        if not segments:
            raise ValueError("Impossible d'extraire la transcription de cette vidéo.")

        job["step"] = "Analyse des moments viraux par Gemini..."
        job["updated_at"] = datetime.now().isoformat()
        analysis = analyze_video_for_viral_clips(metadata, segments)

        job["clips"] = [clip.model_dump() for clip in analysis.clips]

        if not auto_render or not analysis.clips:
            job["status"] = "completed"
            job["step"] = f"Analyse terminée : {len(analysis.clips)} moments viraux détectés."
            job["updated_at"] = datetime.now().isoformat()
            return

        # Rendu séquentiel automatique des clips
        job["rendered_clips"] = []
        for idx, clip in enumerate(analysis.clips):
            job["step"] = f"Rendu du Short #{idx + 1}/{len(analysis.clips)} ({crop_mode})..."
            job["updated_at"] = datetime.now().isoformat()

            clean_id = metadata.video_id
            raw_video = TEMP_DIR / f"{clean_id}_clip_{idx}_{job_id[:6]}.mp4"
            ass_sub = TEMP_DIR / f"{clean_id}_sub_{idx}_{job_id[:6]}.ass"
            
            timestamp_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            short_filename = f"{clean_id}_short_{idx + 1}_{timestamp_id}"
            out_mp4 = OUTPUT_DIR / f"{short_filename}.mp4"
            out_meta = OUTPUT_DIR / f"{short_filename}.json"

            try:
                # 1. Téléchargement ciblé
                download_video_segment(url, clip.start_time, clip.end_time, raw_video)
                # 2. Sous-titres ASS
                generate_ass_subtitles(segments, clip.start_time, clip.end_time, ass_sub)
                # 3. Rendu 9:16 FFmpeg avec face-tracking
                render_vertical_short(raw_video, ass_sub, out_mp4, crop_mode=crop_mode)

                # 4. Métadonnées du Short
                meta_payload = {
                    "id": short_filename,
                    "source_url": url,
                    "source_title": metadata.title,
                    "source_channel": metadata.channel,
                    "clip_index": idx + 1,
                    "crop_mode": crop_mode,
                    "clip": clip.model_dump(),
                    "created_at": datetime.now().isoformat(),
                    "output_file": str(out_mp4)
                }
                with open(out_meta, "w", encoding="utf-8") as f:
                    json.dump(meta_payload, f, ensure_ascii=False, indent=2)

                job["rendered_clips"].append(short_filename)
            finally:
                if raw_video.exists():
                    raw_video.unlink()
                if ass_sub.exists():
                    ass_sub.unlink()

        job["status"] = "completed"
        job["step"] = f"Tous les Shorts ont été générés avec succès ({len(job['rendered_clips'])} vidéos)."
        job["updated_at"] = datetime.now().isoformat()

    except Exception as e:
        err_msg = str(e)
        if "The page needs to be reloaded" in err_msg:
            err_msg = "YouTube a renvoyé 'The page needs to be reloaded'. Vos cookies sont expirés, incomplets ou ont été exportés sans recharger la page. Veuillez réexporter des cookies frais depuis youtube.com (en rechargeant avec F5 avant)."
        elif "Sign in to confirm you’re not a bot" in err_msg or "confirm you're not a bot" in err_msg.lower():
            err_msg = "YouTube exige une authentification (protection anti-bot VPS). Veuillez renseigner vos cookies YouTube via le bouton 'Cookies YouTube' en haut de la page."
        
        job["status"] = "failed"
        job["error"] = err_msg
        job["step"] = f"Erreur : {err_msg}"
        job["updated_at"] = datetime.now().isoformat()

def delete_short_files(short_id: str):
    """Supprime immédiatement les fichiers MP4 et JSON d'un short"""
    mp4_path = OUTPUT_DIR / f"{short_id}.mp4"
    json_path = OUTPUT_DIR / f"{short_id}.json"
    if mp4_path.exists():
        mp4_path.unlink()
    if json_path.exists():
        json_path.unlink()

# --- ROUTES API ---

@app.get("/api/health")
def health():
    js_rt = find_js_runtime()
    node_exec = {}
    if "node" in js_rt and "path" in js_rt["node"]:
        try:
            import subprocess
            r = subprocess.run([js_rt["node"]["path"], "-v"], capture_output=True, text=True, timeout=5)
            node_exec = {"ok": r.returncode == 0, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
        except Exception as ex:
            node_exec = {"error": str(ex)}

    return {
        "status": "ok",
        "has_gemini_key": bool(GEMINI_API_KEY and "your_gemini_api_key_here" not in GEMINI_API_KEY),
        "has_cookies": has_youtube_cookies(),
        "js_runtime": js_rt,
        "node_exec": node_exec,
        "ffmpeg": shutil.which("ffmpeg"),
        "output_dir": str(OUTPUT_DIR),
        "total_shorts": len(list(OUTPUT_DIR.glob("*.json")))
    }

@app.get("/api/cookies")
def get_cookies_status():
    """Vérifie l'état actuel des cookies YouTube sur le serveur"""
    configured = has_youtube_cookies()
    file_size = COOKIES_FILE.stat().st_size if configured else 0
    modified_at = datetime.fromtimestamp(COOKIES_FILE.stat().st_mtime).isoformat() if configured else None
    return {
        "configured": configured,
        "file_path": str(COOKIES_FILE.name),
        "file_size_bytes": file_size,
        "modified_at": modified_at,
    }

@app.post("/api/cookies")
def save_cookies(payload: CookiesPayload):
    """Enregistre le contenu d'un fichier cookies.txt envoyé depuis le tableau de bord"""
    raw_content = payload.content.strip()
    if not raw_content:
        raise HTTPException(status_code=400, detail="Le contenu des cookies ne peut pas être vide")
    
    try:
        COOKIES_FILE.write_text(raw_content, encoding="utf-8")
        return {
            "status": "success",
            "message": "Cookies YouTube enregistrés avec succès !",
            "size": len(raw_content),
            "configured": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'enregistrement : {e}")

@app.delete("/api/cookies")
def delete_cookies():
    """Supprime le fichier de cookies actuel"""
    if COOKIES_FILE.exists():
        COOKIES_FILE.unlink()
    return {"status": "deleted", "configured": False}

@app.post("/api/cookies/test")
def test_youtube_connection(req: CookieTestRequest):
    """Teste la validité de la session YouTube avec les cookies actuels"""
    test_url = sanitize_youtube_url(req.url or "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    try:
        ydl_opts = {
            **get_base_ydl_opts(),
            'skip_download': True,
        }
        info = run_ydl_with_fallback(ydl_opts, lambda ydl: ydl.extract_info(test_url, download=False))
        return {
                "success": True,
                "title": info.get("title", ""),
                "channel": info.get("uploader", ""),
                "duration": info.get("duration", 0),
                "message": f"Session YouTube validée avec succès ! (Vidéo test : {info.get('title')})"
            }
    except Exception as e:
        err = str(e)
        hint = "Vérifiez que votre fichier cookies.txt contient une session active."
        if "The page needs to be reloaded" in err:
            hint = "YouTube a rejeté la session ('The page needs to be reloaded'). Assurez-vous d'avoir rechargé la page YouTube dans votre navigateur (F5), vérifiez qu'aucune bannière d'avertissement n'est affichée, puis réexportez."
        elif "Sign in to confirm you’re not a bot" in err or "confirm you're not a bot" in err.lower():
            hint = "YouTube ne trouve pas de session de compte connecté dans ces cookies. Connectez-vous sur youtube.com avant d'exporter."
        return {
            "success": False,
            "error": err,
            "hint": hint
        }


@app.post("/api/analyze")
def start_analysis(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    if not req.url:
        raise HTTPException(status_code=400, detail="URL requise")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "url": req.url,
        "crop_mode": req.crop_mode,
        "status": "queued",
        "step": "En file d'attente...",
        "created_at": datetime.now().isoformat(),
        "clips": [],
        "rendered_clips": [],
        "error": None
    }

    background_tasks.add_task(
        run_pipeline_task,
        job_id=job_id,
        url=req.url,
        crop_mode=req.crop_mode,
        auto_render=req.auto_render
    )

    return {"job_id": job_id, "status": "queued"}

@app.get("/api/jobs")
def list_jobs():
    return list(jobs.values())[::-1]

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job introuvable")
    return jobs[job_id]

@app.get("/api/shorts")
def list_shorts():
    """Liste tous les Shorts prêts à être téléchargés"""
    shorts_list = []
    for meta_file in sorted(OUTPUT_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            mp4_file = OUTPUT_DIR / f"{meta_file.stem}.mp4"
            if mp4_file.exists():
                data["file_size_mb"] = round(mp4_file.stat().st_size / (1024 * 1024), 2)
                data["exists"] = True
                shorts_list.append(data)
            else:
                # Fichier MP4 manquant
                continue
        except Exception:
            continue
    return shorts_list

@app.get("/api/shorts/{short_id}/video")
def stream_short_video(short_id: str):
    """Stream le fichier vidéo pour lecture directe dans le lecteur web"""
    mp4_path = OUTPUT_DIR / f"{short_id}.mp4"
    if not mp4_path.exists():
        raise HTTPException(status_code=404, detail="Vidéo introuvable")
    return FileResponse(path=mp4_path, media_type="video/mp4")

@app.get("/api/shorts/{short_id}/download")
def download_short(
    short_id: str, 
    background_tasks: BackgroundTasks, 
    delete_after: bool = Query(False, description="Supprimer le fichier après téléchargement pour libérer le disque")
):
    """Télécharge le fichier Short et le supprime éventuellement du VPS pour économiser l'espace disque"""
    mp4_path = OUTPUT_DIR / f"{short_id}.mp4"
    if not mp4_path.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable")

    filename = f"{short_id}.mp4"
    
    if delete_after:
        # Programmer la suppression du fichier juste après la fin du transfert
        background_tasks.add_task(delete_short_files, short_id)

    return FileResponse(
        path=mp4_path,
        media_type="application/octet-stream",
        filename=filename
    )

@app.delete("/api/shorts/{short_id}")
def delete_short(short_id: str):
    """Suppression manuelle d'un Short du disque"""
    mp4_path = OUTPUT_DIR / f"{short_id}.mp4"
    json_path = OUTPUT_DIR / f"{short_id}.json"
    
    if not mp4_path.exists() and not json_path.exists():
        raise HTTPException(status_code=404, detail="Short introuvable")

    delete_short_files(short_id)
    return {"status": "deleted", "id": short_id}

@app.post("/api/shorts/purge-all")
def purge_all_shorts():
    """Supprime tous les fichiers dans output/ pour libérer tout l'espace disque"""
    count = 0
    for f in OUTPUT_DIR.glob("*.*"):
        f.unlink(missing_ok=True)
        count += 1
    return {"status": "purged", "deleted_files": count}

# Montage du frontend compilé s'il existe
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
