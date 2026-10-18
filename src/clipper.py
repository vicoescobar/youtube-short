import subprocess
import os
from pathlib import Path
from typing import List, Optional
import yt_dlp
from yt_dlp.utils import download_range_func
from rich.console import Console

from src.config import TEMP_DIR, OUTPUT_DIR, get_base_ydl_opts, run_ydl_with_fallback
from src.models import TranscriptSegment, ViralClipRecommendation
from src.tracker import compute_smart_crop_expression
from src.extractor import sanitize_youtube_url

console = Console()

def to_ass_timestamp(seconds: float) -> str:
    """Convertit des secondes en format ASS (H:MM:SS.cc)"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    csecs = int(round((seconds - int(seconds)) * 100))
    if csecs >= 100:
        csecs = 99
    return f"{hrs}:{mins:02d}:{secs:02d}.{csecs:02d}"

def generate_ass_subtitles(
    segments: List[TranscriptSegment],
    clip_start: float,
    clip_end: float,
    output_ass_path: Path
) -> None:
    """
    Génère un fichier de sous-titres ASS stylisé pour YouTube Shorts (9:16).
    - Texte en gras, jaune éclatant avec contour noir épais
    - Positionné au tiers inférieur (au-dessus des boutons de l'interface YouTube Shorts)
    - Découpage par phrases courtes pour maximiser la rétention visuelle.
    """
    ass_header = """[Script Info]
Title: YouTube Shorts Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralStyle,Liberation Sans,58,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5.0,2.0,2,40,40,360,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Filtrer les segments qui chevauchent l'extrait [clip_start, clip_end]
    relevant_segments = [
        s for s in segments 
        if s.end > clip_start and s.start < clip_end
    ]

    dialogues = []
    for s in relevant_segments:
        # Recalage du temps par rapport au début du clip (t = 0)
        seg_start = max(0.0, s.start - clip_start)
        seg_end = min(clip_end - clip_start, s.end - clip_start)

        if seg_end <= seg_start:
            continue

        text = s.text.strip().upper()
        # Échappement des caractères spéciaux ASS
        text = text.replace("{", "\\{").replace("}", "\\}")

        start_str = to_ass_timestamp(seg_start)
        end_str = to_ass_timestamp(seg_end)
        dialogues.append(
            f"Dialogue: 0,{start_str},{end_str},ViralStyle,,0,0,0,,{text}"
        )

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header)
        f.write("\n".join(dialogues))
        f.write("\n")

def download_video_segment(
    url: str,
    start_time: float,
    end_time: float,
    output_raw_video: Path
) -> None:
    """
    Télécharge UNIQUEMENT l'extrait vidéo ciblé (30-60s) via yt-dlp.
    Utilise le cut exact sans forcer sur les keyframes pour éviter tout décalage audio/vidéo.
    """
    console.print(f"[cyan]Téléchargement ciblé du segment [{start_time:.2f}s -> {end_time:.2f}s]...[/cyan]")

    ydl_opts = {
        **get_base_ydl_opts(),
        'format': 'bestvideo[vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/bestvideo+bestaudio/best',
        'outtmpl': str(output_raw_video),
        'download_ranges': download_range_func(None, [(start_time, end_time)]),
    }

    if output_raw_video.exists():
        output_raw_video.unlink()

    clean_url = sanitize_youtube_url(url)
    run_ydl_with_fallback(ydl_opts, lambda ydl: ydl.download([clean_url]))

def render_vertical_short(
    raw_video_path: Path,
    ass_subtitles_path: Path,
    output_short_path: Path,
    crop_mode: str = "crop"
) -> Path:
    """
    Rendu vidéo au format vertical 9:16 (1080x1920) avec FFmpeg :
    - Mode 'crop' : Recadrage plein écran 9:16 centré intelligemment sur le visage (MediaPipe).
    - Mode 'blur' : Fond flouté 9:16 avec vidéo 16:9 au centre.
    - Incrustation des sous-titres animés ASS.
    """
    console.print(f"[bold cyan]Rendu vidéo vertical 9:16 (Mode: {crop_mode}) avec sous-titres...[/bold cyan]")

    escaped_ass_path = str(ass_subtitles_path).replace("\\", "/").replace(":", "\\:")

    if crop_mode == "crop":
        # Analyse des visages pour cadrer parfaitement sur l'orateur (même s'il est excentré)
        smart_x_expr = compute_smart_crop_expression(raw_video_path)
        filter_complex = (
            f"[0:v]crop=w=ih*9/16:h=ih:x='{smart_x_expr}':y=0,scale=1080:1920:flags=lanczos,ass='{escaped_ass_path}'[v]"
        )
    else:
        # Mode avec fond flouté étiré
        filter_complex = (
            "[0:v]split=2[bg][fg];"
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:25[blurred];"
            "[fg]scale=1080:-2[foreground];"
            "[blurred][foreground]overlay=(W-w)/2:(H-h)/2[merged];"
            f"[merged]ass='{escaped_ass_path}'[v]"
        )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(raw_video_path),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "veryfast",  # Léger pour le VPS
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_short_path)
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        console.print(f"[red]Erreur lors du rendu FFmpeg :[/red]\n{result.stderr}")
        raise RuntimeError(f"Échec de l'encodage FFmpeg : {result.stderr[-400:]}")

    console.print(f"[bold green]✓ Short généré avec succès : {output_short_path.name}[/bold green]")
    return output_short_path
