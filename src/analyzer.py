import json
from typing import List, Optional
from google import genai
from google.genai import types
from rich.console import Console

from src.config import GEMINI_API_KEY
from src.models import (
    TranscriptSegment,
    VideoMetadata,
    ViralAnalysisResult,
    ViralClipRecommendation,
)
from src.extractor import format_transcript_for_prompt, snap_clip_to_sentence_boundaries

console = Console()

ANALYSIS_SYSTEM_INSTRUCTION = """
Tu es le meilleur expert mondial en stratégie de contenu court (YouTube Shorts, TikTok, Instagram Reels).
Ton objectif est d'analyser la transcription complète d'une vidéo YouTube (avec ses timestamps) pour identifier les 1 à 3 MEILLEURS moments viraux (entre 30 et 60 secondes).

Règles impératives de détection :
1. LE HOOK (L'ACCROCHE) : Le clip DOIT démarrer immédiatement à 00:00 par une phrase choc, une question intrigante, un désaccord, une émotion forte ou une punchline. JAMAIS de transition molle, de "bonjour à tous" ou de blanc.
2. UNE UNITÉ DE SENS COMPLÈTE : Le clip doit raconter une histoire ou exposer une idée complète (problème -> développement -> conclusion/chute). Il ne doit JAMAIS couper au milieu d'une phrase.
3. DURÉE STRICTE : Chaque extrait doit faire impérativement entre 30 et 60 secondes (end_time - start_time >= 30 et <= 60).
4. TITRE YOUTUBE SHORTS : Doit susciter une curiosité irrépressible, utiliser des mots forts en majuscules et 1 ou 2 emojis (moins de 60 caractères).
5. HASHTAGS & DESCRIPTION : 4 à 6 hashtags populaires (#shorts, #viral, + tags thématiques) et une courte description incitant aux commentaires.
6. SCORE DE VIRALITÉ : Note réaliste sur 10 basée sur le potentiel de rétention et de partage.
"""

def analyze_video_for_viral_clips(
    metadata: VideoMetadata,
    segments: List[TranscriptSegment],
    model_name: str = "gemini-3.8-flash"
) -> ViralAnalysisResult:
    """
    Envoie la transcription horodatée à Gemini pour repérer les moments viraux.
    """
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY n'est pas renseignée dans ton fichier .env !\n"
            "Rends-toi sur https://aistudio.google.com/ pour en créer une gratuitement."
        )

    client = genai.Client(api_key=GEMINI_API_KEY)

    formatted_transcript = format_transcript_for_prompt(segments)
    
    prompt = f"""
Voici les informations de la vidéo source :
- Titre : {metadata.title}
- Chaîne : {metadata.channel}
- Durée totale : {metadata.duration} secondes ({metadata.duration // 60} minutes)
- URL : {metadata.webpage_url}

Voici la transcription intégrale avec les timestamps :
---
{formatted_transcript}
---

Identifie les 1 à 3 extraits les plus captivants et viraux respectant les critères stricts de durée (30s à 60s) et de rétention.
"""

    console.print(f"[cyan]Analyse virale en cours avec Gemini ({model_name})...[/cyan]")

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=ANALYSIS_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=ViralAnalysisResult,
                temperature=0.3, # Déterministe et précis sur les timestamps
            ),
        )
    except Exception as e:
        # Fallback sur gemini-2.0-flash si gemini-3.8-flash n'est pas dispo
        if "not found" in str(e).lower() and model_name != "gemini-2.0-flash":
            console.print(f"[yellow]Modèle {model_name} indisponible, bascule sur gemini-2.0-flash...[/yellow]")
            return analyze_video_for_viral_clips(metadata, segments, model_name="gemini-2.0-flash")
        raise e

    result_text = response.text
    if not result_text:
        raise ValueError("Réponse vide reçue de l'API Gemini.")

    data = json.loads(result_text)
    result = ViralAnalysisResult.model_validate(data)

    # Recalage chirurgical des timestamps sur les débuts et fins de phrase réels
    for clip in result.clips:
        orig_start, orig_end = clip.start_time, clip.end_time
        snapped_start, snapped_end = snap_clip_to_sentence_boundaries(
            orig_start, orig_end, segments
        )
        clip.start_time = snapped_start
        clip.end_time = snapped_end

    return result
