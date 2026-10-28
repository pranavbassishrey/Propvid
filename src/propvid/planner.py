"""Timeline planning, scene durations, and image/motion assignment."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from propvid.inputs import ValidImage
from propvid.schema import PlannedScene, PropertyInput, Script, VideoPlan

logger = logging.getLogger(__name__)

MOTION_PRESETS = ["zoom_in", "zoom_out", "pan_left", "pan_right"]
CROSSFADE_OVERLAP = 0.5  # seconds
BASE_MIN_DURATION = 3.5
RAISED_MIN_DURATION = 4.5
MAX_SCENE_DURATION = 7.0
MAX_TITLE_CTA_DURATION = 8.0
WORDS_PER_SECOND = 2.6


def clamp(val: float, min_val: float, max_val: float) -> float:
    """Clamp value between min_val and max_val."""
    return max(min_val, min(val, max_val))


def plan_timeline(
    prop: PropertyInput,
    script: Script,
    valid_images: List[ValidImage],
    resolution: Tuple[int, int] = (1280, 720),
    fps: int = 24,
    narration_durations: Optional[Dict[str, float]] = None,
) -> Tuple[VideoPlan, List[str]]:
    """Calculate scene timings, assign images, and select motion presets.

    Strictly conforms to duration constraints:
    - Drops trailing feature scenes if total duration > 40s (never drops title or CTA).
    - If total < 20s, raises minimum scene duration to 4.5s.
    - If still under 20s, extends title and CTA hold times up to 8s each.
    - If still under 20s, relaxes the 20s floor with a logged warning. Never creates filler scenes.
    """
    warnings: List[str] = []
    scenes = list(script.scenes)
    narration_durations = narration_durations or {}

    # Helper to compute initial scene duration
    def get_initial_duration(scene) -> float:
        if scene.id in narration_durations:
            speech_sec = narration_durations[scene.id]
        else:
            word_count = len(scene.narration.split())
            speech_sec = word_count / WORDS_PER_SECOND
        return clamp(speech_sec + 0.6, BASE_MIN_DURATION, MAX_SCENE_DURATION)

    # 1. Total duration > 40s check: drop trailing feature scenes if needed
    while len(scenes) > 2:
        durations = [get_initial_duration(s) for s in scenes]
        total_time = sum(durations) - CROSSFADE_OVERLAP * (len(scenes) - 1)
        if total_time <= 40.0:
            break
        # Find last feature scene before CTA (CTA is last scene)
        feature_indices = [i for i, s in enumerate(scenes) if s.kind in ("feature", "highlight")]
        if not feature_indices:
            break
        drop_idx = feature_indices[-1]
        dropped_scene = scenes.pop(drop_idx)
        warnings.append(f"Dropped trailing feature scene '{dropped_scene.headline}' to keep video under 40s.")

    # 2. Compute durations with base minimum
    durations = [get_initial_duration(s) for s in scenes]
    total_time = sum(durations) - CROSSFADE_OVERLAP * (len(scenes) - 1)

    # 3. If total < 20s, raise minimum scene duration to 4.5s
    if total_time < 20.0:
        durations = [
            clamp(
                (narration_durations.get(s.id, len(s.narration.split()) / WORDS_PER_SECOND) + 0.6),
                RAISED_MIN_DURATION,
                MAX_SCENE_DURATION,
            )
            for s in scenes
        ]
        total_time = sum(durations) - CROSSFADE_OVERLAP * (len(scenes) - 1)

    # 4. If under 20s, extend lone highlight up to 7s, and Title/CTA hold times up to 8s each
    # Target 21.0s to ensure a comfortable safety margin above the 20s floor
    if total_time < 20.0 and len(durations) >= 2:
        shortfall = 21.0 - total_time

        # Check for lone highlight scene and extend up to 7s
        for idx, s in enumerate(scenes):
            if s.kind == "highlight":
                highlight_headroom = MAX_SCENE_DURATION - durations[idx]
                h_add = min(shortfall, max(0.0, highlight_headroom))
                durations[idx] += h_add
                shortfall -= h_add
                break

        # Extend title up to 8.0s
        if shortfall > 0:
            title_headroom = MAX_TITLE_CTA_DURATION - durations[0]
            title_add = min(shortfall, max(0.0, title_headroom))
            durations[0] += title_add
            shortfall -= title_add

        # Then extend CTA up to 8.0s
        if shortfall > 0:
            cta_headroom = MAX_TITLE_CTA_DURATION - durations[-1]
            cta_add = min(shortfall, max(0.0, cta_headroom))
            durations[-1] += cta_add
            shortfall -= cta_add

        total_time = sum(durations) - CROSSFADE_OVERLAP * (len(scenes) - 1)

    # 5. If still strictly below 20s (with floating point tolerance), relax floor with warning
    if total_time < (20.0 - 1e-6):
        warn_msg = (
            f"Total video duration ({total_time:.1f}s) is below target 20s after extending hold times. "
            f"Preserving authentic content without inventing filler scenes."
        )
        logger.warning(warn_msg)
        warnings.append(warn_msg)

    # 6. Assign images and motion presets
    planned_scenes: List[PlannedScene] = []
    used_images: List[Path] = []
    image_motion_history: Dict[Path, int] = {}
    current_time = 0.0

    # Index valid images by associated feature
    feature_to_image: Dict[str, ValidImage] = {}
    for img in valid_images:
        if img.feature:
            feature_to_image[img.feature.strip().lower()] = img

    num_images = len(valid_images)

    for i, (scene, dur) in enumerate(zip(scenes, durations)):
        # Select image
        assigned_img: ValidImage
        if scene.kind == "title":
            assigned_img = valid_images[0]
        elif scene.kind == "cta":
            assigned_img = valid_images[-1]
        else:
            # Feature or highlight scene
            matched = feature_to_image.get(scene.headline.strip().lower())
            if matched:
                assigned_img = matched
            else:
                # Next unused or cycle through images
                unused = [img for img in valid_images if img.path not in used_images]
                if unused:
                    assigned_img = unused[0]
                else:
                    assigned_img = valid_images[i % num_images]

        img_path = assigned_img.path
        used_images.append(img_path)

        # Select motion preset (cycle, ensuring different preset on reuse)
        preset_idx = image_motion_history.get(img_path, i) % len(MOTION_PRESETS)
        if img_path in image_motion_history:
            preset_idx = (image_motion_history[img_path] + 1) % len(MOTION_PRESETS)
        image_motion_history[img_path] = preset_idx
        motion = MOTION_PRESETS[preset_idx]

        planned_scenes.append(
            PlannedScene(
                spec=scene,
                image_path=img_path,
                start=current_time,
                duration=dur,
                motion=motion,
            )
        )

        # Increment timeline taking crossfade into account
        current_time += dur - CROSSFADE_OVERLAP

    # True total video duration is the end of the last scene
    final_duration = planned_scenes[-1].start + planned_scenes[-1].duration

    plan = VideoPlan(
        scenes=planned_scenes,
        total_duration=final_duration,
        resolution=resolution,
        fps=fps,
        warnings=warnings,
    )
    return plan, warnings
