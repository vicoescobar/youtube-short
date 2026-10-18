from typing import List, Optional
from pydantic import BaseModel, Field

class TranscriptSegment(BaseModel):
    """Segment de transcription horodaté"""
    start: float = Field(..., description="Début du segment en secondes")
    end: float = Field(..., description="Fin du segment en secondes")
    text: str = Field(..., description="Texte prononcé pendant le segment")

class VideoMetadata(BaseModel):
    """Métadonnées de la vidéo YouTube source"""
    video_id: str
    title: str
    channel: str
    duration: int
    webpage_url: str

class ViralClipRecommendation(BaseModel):
    """Recommandation d'un extrait à fort potentiel viral détecté par l'IA"""
    title: str = Field(..., description="Titre percutant pour le Short (max 60 carac, emojis, majuscules percutantes)")
    start_time: float = Field(..., description="Timestamp de début précis en secondes")
    end_time: float = Field(..., description="Timestamp de fin précis en secondes")
    hook_summary: str = Field(..., description="L'accroche des 3 premières secondes qui retient l'attention")
    virality_score: float = Field(..., description="Note de viralité estimée de 0.0 à 10.0")
    justification: str = Field(..., description="Pourquoi cet extrait va performer (émotion, clivage, surprise, humour, conseil)")
    hashtags: List[str] = Field(default_factory=list, description="Liste de 4-6 hashtags optimisés SEO")
    description: str = Field(..., description="Description optimisée pour YouTube Shorts")

class ViralAnalysisResult(BaseModel):
    """Résultat complet de l'analyse d'une vidéo"""
    clips: List[ViralClipRecommendation] = Field(
        default_factory=list,
        description="Liste des meilleurs extraits de 30 à 60 secondes classés par score de viralité décroissant (jusqu'au nombre maximum demandé)"
    )
