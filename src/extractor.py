import json
import re
import os
import math
import time
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
import yt_dlp
from rich.console import Console

from src.config import TEMP_DIR, GROQ_API_KEY, get_base_ydl_opts, run_ydl_with_fallback
from src.models import TranscriptSegment, VideoMetadata

console = Console()

def format_timestamp(seconds: float) -> str:
    """Convertit des secondes en format HH:MM:SS"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"

def sanitize_youtube_url(url: str) -> str:
    """Nettoie l'URL YouTube en ne gardant que l'identifiant propre sans tracking (&pp=, &si=, &feature=...)"""
    match = re.search(r"(?:v=|\/live\/|\/shorts\/|youtu\.be\/|\/v\/|embed\/)([a-zA-Z0-9_-]{11})", url)
    if match:
        video_id = match.group(1)
        return f"https://www.youtube.com/watch?v={video_id}"
    return url.strip()

def get_video_metadata(url: str) -> VideoMetadata:
    """Récupère les informations de base de la vidéo sans rien télécharger"""
    clean_url = sanitize_youtube_url(url)
    ydl_opts = {
        **get_base_ydl_opts(),
        'skip_download': True,
        'check_formats': False,
    }
    info = run_ydl_with_fallback(ydl_opts, lambda ydl: ydl.extract_info(clean_url, download=False))
    return VideoMetadata(
            video_id=info.get('id', ''),
            title=info.get('title', 'Sans titre'),
            channel=info.get('uploader', 'Chaîne inconnue'),
            duration=int(info.get('duration', 0)),
            webpage_url=info.get('webpage_url', clean_url)
        )

def _parse_json3_subtitles(file_path: Path) -> List[TranscriptSegment]:
    """Parse un fichier de sous-titres YouTube au format json3"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    segments: List[TranscriptSegment] = []
    events = data.get("events", [])
    for ev in events:
        start_ms = ev.get("tStartMs", 0)
        duration_ms = ev.get("dDurationMs", 0)
        segs = ev.get("segs", [])
        text = "".join(s.get("utf8", "") for s in segs).strip()
        
        # Ignorer les sauts de ligne ou segments vides
        if not text or text == "\n":
            continue
            
        start_sec = start_ms / 1000.0
        end_sec = (start_ms + duration_ms) / 1000.0
        segments.append(TranscriptSegment(start=start_sec, end=end_sec, text=text))
    return segments

def _parse_vtt_subtitles(file_path: Path) -> List[TranscriptSegment]:
    """Parse basique d'un fichier WebVTT"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match de type: 00:01:23.456 --> 00:01:25.789
    pattern = re.compile(r"(\d{2}:)?(\d{2}):(\d{2})[\.,](\d{3})\s*-->\s*(\d{2}:)?(\d{2}):(\d{2})[\.,](\d{3})\s*\n(.*?)(?=\n\n|\n\d|\Z)", re.DOTALL)
    
    segments: List[TranscriptSegment] = []
    for match in pattern.finditer(content):
        # Calcul temps début
        h1 = int(match.group(1)[:-1]) if match.group(1) else 0
        m1 = int(match.group(2))
        s1 = int(match.group(3))
        ms1 = int(match.group(4))
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0

        # Calcul temps fin
        h2 = int(match.group(5)[:-1]) if match.group(5) else 0
        m2 = int(match.group(6))
        s2 = int(match.group(7))
        ms2 = int(match.group(8))
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0

        raw_text = match.group(9).strip()
        # Supprimer les balises HTML éventuelles
        text = re.sub(r"<[^>]+>", "", raw_text).replace("\n", " ").strip()
        if text:
            segments.append(TranscriptSegment(start=start, end=end, text=text))
    return segments

def _extract_youtube_subtitles(url: str, video_id: str) -> Optional[List[TranscriptSegment]]:
    """Tente de récupérer les sous-titres directement depuis YouTube sans télécharger la vidéo"""
    sub_tmpl = str(TEMP_DIR / f"{video_id}_sub.%(ext)s")
    
    ydl_opts = {
        **get_base_ydl_opts(),
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['fr', 'en', 'auto'],
        'subtitlesformat': 'json3/vtt',
        'outtmpl': sub_tmpl,
    }
    
    try:
        run_ydl_with_fallback(ydl_opts, lambda ydl: ydl.download([url]))
    except Exception as e:
        console.print(f"[yellow]Avertissement lors de l'extraction des sous-titres : {e}[/yellow]")
        return None

    # Chercher les fichiers générés
    for ext in ["json3", "vtt"]:
        files = list(TEMP_DIR.glob(f"{video_id}_sub*.{ext}"))
        if files:
            target_file = files[0]
            try:
                if ext == "json3":
                    segs = _parse_json3_subtitles(target_file)
                else:
                    segs = _parse_vtt_subtitles(target_file)
                # Nettoyage
                for f in files:
                    f.unlink(missing_ok=True)
                if segs:
                    return segs
            except Exception as parse_err:
                console.print(f"[red]Erreur de parsing {ext}: {parse_err}[/red]")
                for f in files:
                    f.unlink(missing_ok=True)

    return None

def get_audio_duration(audio_path: Path) -> float:
    """Récupère la durée exacte en secondes d'un fichier audio via ffprobe"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0

def _transcribe_audio_chunk(client, chunk_path: Path, offset_seconds: float) -> List[TranscriptSegment]:
    """Transcrit un morceau audio précis et décale ses timestamps de l'offset"""
    with open(chunk_path, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(chunk_path.name, file.read()),
            model="whisper-large-v3",
            response_format="verbose_json"
        )

    segments: List[TranscriptSegment] = []
    raw_segments = getattr(transcription, "segments", [])
    if isinstance(raw_segments, list):
        for s in raw_segments:
            start = float(s.get("start", 0.0) if isinstance(s, dict) else getattr(s, "start", 0.0))
            end = float(s.get("end", 0.0) if isinstance(s, dict) else getattr(s, "end", 0.0))
            text = str(s.get("text", "") if isinstance(s, dict) else getattr(s, "text", "")).strip()
            if text:
                segments.append(TranscriptSegment(
                    start=round(start + offset_seconds, 2),
                    end=round(end + offset_seconds, 2),
                    text=text
                ))
    return segments

def _transcribe_with_groq(audio_path: Path) -> List[TranscriptSegment]:
    """
    Transcrit l'audio via l'API Groq (Whisper-large-v3).
    Si le fichier dépasse 20 Mo ou 15 minutes, il est automatiquement découpé
    en morceaux de 10 minutes traités séquentiellement pour contourner la limite de 25 Mo.
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY non renseignée dans le fichier .env !")

    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)

    file_size_mb = audio_path.stat().st_size / (1024 * 1024)
    duration = get_audio_duration(audio_path)

    CHUNK_DURATION_SEC = 600.0  # 10 minutes par morceau (~3.5 Mo par morceau à 48 kbps mono)

    # 1. Cas simple : petit fichier < 20 Mo et < 15 min -> 1 seule requête directe
    if file_size_mb < 20.0 and duration <= 900.0:
        console.print(f"[cyan]Envoi direct de l'audio à Groq ({file_size_mb:.1f} Mo, {duration/60:.1f} min)...[/cyan]")
        return _transcribe_audio_chunk(client, audio_path, offset_seconds=0.0)

    # 2. Cas des vidéos longues : découpage en morceaux de 10 min
    num_chunks = int(math.ceil(duration / CHUNK_DURATION_SEC))
    console.print(
        f"[cyan]Vidéo longue ({duration/60:.1f} min, {file_size_mb:.1f} Mo) : "
        f"Découpage en {num_chunks} morceaux de 10 min pour respecter la limite Groq (25 Mo)...[/cyan]"
    )

    all_segments: List[TranscriptSegment] = []

    for i in range(num_chunks):
        chunk_start = i * CHUNK_DURATION_SEC
        chunk_len = min(CHUNK_DURATION_SEC, duration - chunk_start)
        chunk_file = TEMP_DIR / f"{audio_path.stem}_chunk_{i}.mp3"

        t_start_fmt = format_timestamp(chunk_start)
        t_end_fmt = format_timestamp(chunk_start + chunk_len)
        console.print(f"[dim]• Morceau {i+1}/{num_chunks} [{t_start_fmt} -> {t_end_fmt}]...[/dim]")

        # Découpage ultra-léger avec FFmpeg en mono 48k
        subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(chunk_start),
            "-t", str(chunk_len),
            "-i", str(audio_path),
            "-ac", "1",
            "-b:a", "48k",
            str(chunk_file)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        try:
            chunk_segs = _transcribe_audio_chunk(client, chunk_file, offset_seconds=chunk_start)
            all_segments.extend(chunk_segs)
            time.sleep(0.5)  # Pause douce pour respecter les quotas RPM
        finally:
            if chunk_file.exists():
                chunk_file.unlink()

    return all_segments

def extract_transcript(url: str, metadata: VideoMetadata) -> List[TranscriptSegment]:
    """
    Stratégie en 2 temps :
    1. Essaie de récupérer les sous-titres YouTube (0 Mo de vidéo, 1 sec).
    2. Si indisponible, télécharge uniquement la piste audio compressée et transcrit via Groq.
    """
    clean_url = sanitize_youtube_url(url)
    console.print(f"[bold blue]Analyse des sous-titres disponibles pour : {metadata.title}...[/bold blue]")
    segments = _extract_youtube_subtitles(clean_url, metadata.video_id)
    if segments and len(segments) > 5:
        console.print(f"[green]✓ Sous-titres YouTube récupérés avec succès ({len(segments)} segments) sans aucun téléchargement lourd ![/green]")
        return segments

    console.print("[yellow]Sous-titres YouTube indisponibles. Téléchargement audio optimisé (mono 48k)...[/yellow]")
    audio_path = TEMP_DIR / f"{metadata.video_id}.mp3"
    
    ydl_opts = {
        **get_base_ydl_opts(),
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': str(TEMP_DIR / f"{metadata.video_id}.%(ext)s"),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '48', # 48 kbps mono pour minimiser la taille
        }],
        'postprocessor_args': ['-ac', '1'], # Forcer mono pour diviser la taille par 2
    }
    
    try:
        run_ydl_with_fallback(ydl_opts, lambda ydl: ydl.download([clean_url]))
        
        segments = _transcribe_with_groq(audio_path)
        console.print(f"[green]✓ Transcription Groq réussie ({len(segments)} segments) ![/green]")
        return segments
    finally:
        # Nettoyage systématique du fichier audio source
        if audio_path.exists():
            audio_path.unlink()

def format_transcript_for_prompt(segments: List[TranscriptSegment], max_chars: int = 200000) -> str:
    """Formate la transcription avec des timestamps clairs pour l'analyse IA"""
    lines = []
    char_count = 0
    for seg in segments:
        ts = format_timestamp(seg.start)
        line = f"[{ts}] {seg.text}"
        char_count += len(line) + 1
        if char_count > max_chars:
            lines.append("... [Transcription tronquée car trop longue]")
            break
        lines.append(line)
    return "\n".join(lines)

def snap_clip_to_sentence_boundaries(
    start_time: float,
    end_time: float,
    segments: List[TranscriptSegment],
    search_window: float = 4.5
) -> Tuple[float, float]:
    """
    Aligne précisément les timestamps approximatifs fournis par l'IA sur les frontières
    réelles de début et fin de phrase de la transcription mot à mot.
    Évite toute coupure au milieu d'un mot ou d'une phrase.
    """
    if not segments:
        return start_time, end_time

    # 1. Début : caler sur le début du segment le plus proche
    best_start = start_time
    min_start_diff = float("inf")
    for s in segments:
        diff = abs(s.start - start_time)
        if diff <= search_window and diff < min_start_diff:
            min_start_diff = diff
            best_start = s.start

    # 2. Fin : caler sur la fin d'une phrase (ponctuation . ! ?) ou fin de parole
    best_end = end_time
    min_end_diff = float("inf")
    for s in segments:
        diff = abs(s.end - end_time)
        if diff <= search_window:
            ends_sentence = s.text.rstrip().endswith((".", "!", "?"))
            weighted_diff = diff - (0.8 if ends_sentence else 0.0)
            if weighted_diff < min_end_diff:
                min_end_diff = weighted_diff
                best_end = s.end

    if best_end <= best_start:
        best_end = best_start + max(30.0, end_time - start_time)

    # Petite marge de respiration naturelle à la fin (0.25s) pour ne pas tronquer la dernière syllabe
    best_end += 0.25

    return round(best_start, 2), round(best_end, 2)

