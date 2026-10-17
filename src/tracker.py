import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from rich.console import Console

console = Console()

MODEL_PATH = Path(__file__).parent / "models_weights" / "blaze_face_short_range.tflite"

def get_face_detector() -> Optional[vision.FaceDetector]:
    """Initialise le détecteur de visage MediaPipe BlazeFace (225 Ko)"""
    if not MODEL_PATH.exists():
        console.print(f"[yellow]Modèle {MODEL_PATH} introuvable, détection de visage désactivée.[/yellow]")
        return None
    try:
        base_options = python.BaseOptions(model_asset_path=str(MODEL_PATH))
        options = vision.FaceDetectorOptions(base_options=base_options)
        return vision.FaceDetector.create_from_options(options)
    except Exception as e:
        console.print(f"[yellow]Impossible d'initialiser MediaPipe : {e}[/yellow]")
        return None

def compute_smart_crop_expression(
    video_path: Path,
    sample_fps: float = 2.0
) -> str:
    """
    Analyse les visages à 2 frames par seconde avec MediaPipe.
    Génère une expression FFmpeg pour le paramètre 'x' du filtre crop :
    - Si l'orateur est fixe sur un côté (ex: tiers droit), cadre parfaitement sur lui.
    - Si la caméra change de plan en cours de route, bascule automatiquement le cadrage.
    - Si aucun visage n'est détecté, se recentre au milieu par défaut.
    """
    detector = get_face_detector()
    if detector is None:
        return "(in_w-out_w)/2"

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return "(in_w-out_w)/2"

    in_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    in_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    crop_w = int(in_h * 9 / 16)
    if crop_w % 2 != 0:
        crop_w -= 1
    max_x = max(0, in_w - crop_w)
    center_x = max_x // 2

    sample_interval = max(1, int(fps / sample_fps))
    measurements: List[Tuple[float, int]] = [] # (timestamp, crop_x)

    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % sample_interval == 0:
            timestamp = frame_idx / fps
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            
            try:
                res = detector.detect(mp_img)
                if res.detections:
                    # Prendre le visage le plus grand (orateur principal au premier plan)
                    primary_face = max(
                        res.detections, 
                        key=lambda d: d.bounding_box.width * d.bounding_box.height
                    )
                    box = primary_face.bounding_box
                    face_center_x = box.origin_x + (box.width / 2.0)
                    
                    # Calcul du X de recadrage idéal centré sur le visage
                    target_x = int(face_center_x - (crop_w / 2.0))
                    clamped_x = max(0, min(max_x, target_x))
                    measurements.append((timestamp, clamped_x))
                else:
                    # Conserver la dernière position connue ou le centre
                    last_x = measurements[-1][1] if measurements else center_x
                    measurements.append((timestamp, last_x))
            except Exception:
                pass

        frame_idx += 1

    cap.release()

    if not measurements:
        return f"{center_x}"

    # Découpage en plans stables (segmentation si saut de cadrage > 15% de la largeur)
    threshold = int(in_w * 0.15)
    segments: List[Tuple[float, float, int]] = [] # (t_start, t_end, median_x)

    cur_start = measurements[0][0]
    cur_points = [measurements[0][1]]

    for t, x in measurements[1:]:
        if abs(x - cur_points[-1]) > threshold:
            # Changement de plan détecté
            med_x = int(np.median(cur_points))
            segments.append((cur_start, t, med_x))
            cur_start = t
            cur_points = [x]
        else:
            cur_points.append(x)

    # Dernier segment
    if cur_points:
        med_x = int(np.median(cur_points))
        last_t = measurements[-1][0] + 1.0
        segments.append((cur_start, last_t, med_x))

    if len(segments) == 1:
        chosen_x = segments[0][2]
        console.print(f"[green]✓ Orateur détecté et centré à X={chosen_x}px (largeur: {in_w}px)[/green]")
        return f"{chosen_x}"

    # Construction de l'expression FFmpeg conditionnelle if(lt(t, t1), x1, if(lt(t, t2), x2, ...))
    console.print(f"[green]✓ Détection dynamique de {len(segments)} plans de cadrage différents[/green]")
    
    expr = f"{segments[-1][2]}"
    for s_start, s_end, s_x in reversed(segments[:-1]):
        expr = f"if(lt(t,{s_end:.2f}),{s_x},{expr})"

    return expr
