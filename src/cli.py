import argparse
import sys
import json
from pathlib import Path
from typing import List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config import GEMINI_API_KEY, OUTPUT_DIR, TEMP_DIR
from src.extractor import get_video_metadata, extract_transcript, format_timestamp
from src.analyzer import analyze_video_for_viral_clips
from src.clipper import (
    generate_ass_subtitles,
    download_source_video,
    cut_local_video_segment,
    download_video_segment,
    render_vertical_short,
)

console = Console()

def render_single_clip(
    url: str,
    metadata,
    selected_clip,
    clip_index: int,
    segments,
    crop_mode: str,
    source_video: Optional[Path] = None
) -> Path:
    """Télécharge, sous-titre et encode un Short individuel"""
    clip_dur = selected_clip.end_time - selected_clip.start_time
    
    console.print(Panel(
        f"[bold green]🎬 Traitement du Short #{clip_index + 1}[/bold green]\n"
        f"• Titre : {selected_clip.title}\n"
        f"• Intervalle exact : {format_timestamp(selected_clip.start_time)} -> {format_timestamp(selected_clip.end_time)} ({clip_dur:.1f}s)\n"
        f"• Format vertical : [cyan]{crop_mode.upper()}[/cyan] ({'Plein écran 9:16' if crop_mode == 'crop' else 'Fond flouté'})\n"
        f"• Justification : {selected_clip.justification}\n"
        f"• Tags : {' '.join(selected_clip.hashtags)}",
        title=f"Génération Short #{clip_index + 1}",
        border_style="green"
    ))

    clean_id = metadata.video_id
    raw_video_path = TEMP_DIR / f"{clean_id}_clip_{clip_index}.mp4"
    ass_sub_path = TEMP_DIR / f"{clean_id}_sub_{clip_index}.ass"
    output_short_path = OUTPUT_DIR / f"{clean_id}_short_{clip_index + 1}.mp4"
    output_meta_path = OUTPUT_DIR / f"{clean_id}_short_{clip_index + 1}.json"

    try:
        # 1. Découpage local FFmpeg (ou téléchargement ciblé yt-dlp en fallback)
        if source_video and source_video.exists():
            cut_local_video_segment(
                source_video,
                selected_clip.start_time,
                selected_clip.end_time,
                raw_video_path
            )
        else:
            download_video_segment(
                url, 
                selected_clip.start_time, 
                selected_clip.end_time, 
                raw_video_path
            )

        # 2. Génération sous-titres stylisés ASS
        generate_ass_subtitles(
            segments, 
            selected_clip.start_time, 
            selected_clip.end_time, 
            ass_sub_path
        )

        # 3. Rendu 9:16 FFmpeg
        render_vertical_short(
            raw_video_path,
            ass_sub_path,
            output_short_path,
            crop_mode=crop_mode
        )

        # 4. Sauvegarde des métadonnées
        meta_payload = {
            "source_url": url,
            "source_title": metadata.title,
            "clip_index": clip_index + 1,
            "crop_mode": crop_mode,
            "clip": selected_clip.model_dump(),
            "output_file": str(output_short_path)
        }
        with open(output_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_payload, f, ensure_ascii=False, indent=2)

        console.print(
            f"[bold green]✓ Fichier prêt :[/bold green] [cyan]{output_short_path}[/cyan]\n"
        )
        return output_short_path

    finally:
        # Nettoyage des rushs temporaires
        if raw_video_path.exists():
            raw_video_path.unlink()
        if ass_sub_path.exists():
            ass_sub_path.unlink()

def main():
    parser = argparse.ArgumentParser(description="YouTube Shorts Viral Clipper - CLI de test Phase 1")
    parser.add_argument("--url", type=str, help="URL de la vidéo YouTube à analyser")
    parser.add_argument("--render", action="store_true", help="Générer automatiquement sans confirmation")
    parser.add_argument("--all", action="store_true", help="Générer tous les clips détectés")
    parser.add_argument("--clip-index", type=int, default=None, help="Index spécifique du clip (1 pour le premier)")
    parser.add_argument(
        "--crop-mode", 
        type=str, 
        choices=["crop", "blur"], 
        default="crop",
        help="Mode de recadrage vertical : 'crop' (plein écran 9:16) ou 'blur' (fond flouté)"
    )
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold magenta]🎬 YouTube Shorts Viral Clipper - Phase 1[/bold magenta]\n"
        "[dim]Analyse IA (Gemini Flash) & Rendu FFmpeg 9:16 automatique[/dim]",
        border_style="magenta"
    ))

    # 1. Vérification clé API Gemini
    if not GEMINI_API_KEY or "your_gemini_api_key_here" in GEMINI_API_KEY:
        console.print(
            "[bold red]❌ Clé GEMINI_API_KEY manquante ou non configurée ![/bold red]\n"
            "Ouvre le fichier [bold].env[/bold] et renseigne ta clé obtenue gratuitement sur :\n"
            "[underline blue]https://aistudio.google.com/[/underline blue]"
        )
        sys.exit(1)

    url = args.url
    if not url:
        url = console.input("[bold yellow]Colle l'URL de la vidéo YouTube : [/bold yellow]").strip()

    if not url:
        console.print("[red]Aucune URL fournie. Arrêt.[/red]")
        sys.exit(1)

    try:
        # 2. Métadonnées de la vidéo
        with console.status("[bold green]Récupération des métadonnées de la vidéo...[/bold green]"):
            metadata = get_video_metadata(url)

        console.print(f"[bold]Vidéo :[/bold] [cyan]{metadata.title}[/cyan]")
        console.print(f"[bold]Chaîne :[/bold] {metadata.channel} | [bold]Durée :[/bold] {metadata.duration // 60}m {metadata.duration % 60}s\n")

        # 3. Extraction de la transcription
        segments = extract_transcript(url, metadata)
        if not segments:
            console.print("[red]Impossible d'obtenir une transcription pour cette vidéo.[/red]")
            sys.exit(1)

        # 4. Analyse virale avec Gemini + Calage automatique des frontières de phrases
        analysis = analyze_video_for_viral_clips(metadata, segments)

        if not analysis.clips:
            console.print("[yellow]Aucun moment viral répondant aux critères n'a été trouvé.[/yellow]")
            sys.exit(0)

        # 5. Affichage des résultats
        table = Table(title=f"Moments Viraux Détectés ({len(analysis.clips)})", border_style="cyan")
        table.add_column("#", justify="center", style="bold")
        table.add_column("Score", justify="center", style="green")
        table.add_column("Timestamps précis", justify="center")
        table.add_column("Durée", justify="center")
        table.add_column("Titre suggéré", style="bold white")
        table.add_column("Accroche (Hook)", style="dim")

        for idx, clip in enumerate(analysis.clips):
            duration = clip.end_time - clip.start_time
            t_start = format_timestamp(clip.start_time)
            t_end = format_timestamp(clip.end_time)
            table.add_row(
                str(idx + 1),
                f"{clip.virality_score:.1f}/10",
                f"{t_start} -> {t_end}",
                f"{duration:.1f}s",
                clip.title,
                clip.hook_summary[:60] + "..." if len(clip.hook_summary) > 60 else clip.hook_summary
            )

        console.print(table)
        console.print()

        # 6. Sélection des clips à générer
        clips_to_generate: List[int] = []

        if args.all:
            clips_to_generate = list(range(len(analysis.clips)))
        elif args.clip_index is not None:
            idx = args.clip_index - 1
            if 0 <= idx < len(analysis.clips):
                clips_to_generate = [idx]
            else:
                console.print(f"[red]Index {args.clip_index} hors limites (1 à {len(analysis.clips)}).[/red]")
                sys.exit(1)
        elif args.render:
            clips_to_generate = [0]
        else:
            console.print("[bold yellow]Quels Shorts souhaites-tu générer ?[/bold yellow]")
            console.print(" • Tape [bold green]all[/bold green] pour générer TOUS les clips")
            console.print(" • Tape un ou plusieurs numéros séparés par une virgule (ex: [bold cyan]1[/bold cyan] ou [bold cyan]1,2,3[/bold cyan])")
            console.print(" • Appuie sur [bold red]q[/bold red] pour quitter")
            user_choice = console.input("\n[bold]Votre choix (défaut 'all') : [/bold]").strip().lower()

            if user_choice in ["q", "quit", "exit"]:
                console.print("[dim]Opération annulée.[/dim]")
                sys.exit(0)
            elif user_choice in ["", "all", "tous", "a"]:
                clips_to_generate = list(range(len(analysis.clips)))
            else:
                try:
                    parts = [int(p.strip()) - 1 for p in user_choice.split(",") if p.strip()]
                    clips_to_generate = [p for p in parts if 0 <= p < len(analysis.clips)]
                except ValueError:
                    console.print("[yellow]Entrée non reconnue, génération de tous les clips.[/yellow]")
                    clips_to_generate = list(range(len(analysis.clips)))

        if not clips_to_generate:
            console.print("[yellow]Aucun clip sélectionné pour la génération.[/yellow]")
            sys.exit(0)

        # 7. Choix du mode de recadrage (si non passé en argument)
        crop_mode = args.crop_mode
        if not args.render and not args.all:
            mode_input = console.input(
                f"[bold yellow]Mode de cadrage vertical [1: Plein écran 9:16 (recommandé), 2: Fond flouté] (défaut 1) : [/bold yellow]"
            ).strip()
            if mode_input == "2":
                crop_mode = "blur"
            else:
                crop_mode = "crop"

        # 8. Génération séquentielle des clips
        console.print(f"\n[bold cyan]Lancement de la génération de {len(clips_to_generate)} Short(s)...[/bold cyan]\n")

        source_video = None
        if len(clips_to_generate) > 1:
            try:
                source_video_path = TEMP_DIR / f"{metadata.video_id}_source.mp4"
                download_source_video(url, source_video_path)
                if source_video_path.exists() and source_video_path.stat().st_size > 1000:
                    source_video = source_video_path
            except Exception as e:
                console.print(f"[yellow]Téléchargement source global échoué ({e}), fallback par segment...[/yellow]")

        generated_files = []
        try:
            for c_idx in clips_to_generate:
                try:
                    output_file = render_single_clip(
                        url=url,
                        metadata=metadata,
                        selected_clip=analysis.clips[c_idx],
                        clip_index=c_idx,
                        segments=segments,
                        crop_mode=crop_mode,
                        source_video=source_video
                    )
                    generated_files.append(output_file)
                except Exception as clip_err:
                    console.print(f"[bold red]❌ Erreur lors du rendu du Short #{c_idx + 1} :[/bold red] {clip_err}")
        finally:
            if source_video and source_video.exists():
                source_video.unlink()

        console.print(Panel.fit(
            f"[bold green]🎉 Félicitations ! {len(generated_files)} Short(s) généré(s) avec succès :[/bold green]\n" +
            "\n".join([f"• [cyan]{f}[/cyan]" for f in generated_files]),
            border_style="green"
        ))

    except Exception as e:
        console.print(f"[bold red]❌ Erreur durant le traitement :[/bold red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)

if __name__ == "__main__":
    main()
