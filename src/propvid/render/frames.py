"""Stateless frame renderer: Ken Burns motion, overlays, and crossfade blending."""

import math
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from propvid.render.text import render_scene_overlay
from propvid.schema import PlannedScene, VideoPlan

# Cache pre-cropped base images and rendered overlay cards for performance
_IMAGE_CACHE: Dict[Tuple[str, int, int, bool], Image.Image] = {}
_OVERLAY_CACHE: Dict[Tuple[str, int, int], Image.Image] = {}

CROSSFADE_DURATION = 0.5  # seconds
OVERLAY_FADE_IN = 0.4     # seconds
OVERLAY_FADE_OUT = 0.3    # seconds
MARGIN_SCALE = 1.15       # 15% extra headroom for Ken Burns panning/zooming


def _get_base_image(
    image_path: Path,
    width: int,
    height: int,
    is_cta: bool = False,
) -> Image.Image:
    """Load, orient, cover-fit to 1.15x output size, and optionally blur for CTA."""
    cache_key = (str(image_path), width, height, is_cta)
    if cache_key in _IMAGE_CACHE:
        return _IMAGE_CACHE[cache_key]

    target_w = int(round(width * MARGIN_SCALE))
    target_h = int(round(height * MARGIN_SCALE))

    try:
        with Image.open(image_path) as raw_im:
            im = ImageOps.exif_transpose(raw_im).convert("RGB")
    except Exception:
        # Fallback dark background if file read fails
        im = Image.new("RGB", (target_w, target_h), (25, 30, 45))

    # Cover-fit scaling
    src_w, src_h = im.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(round(src_w * scale))
    new_h = int(round(src_h * scale))
    im = im.resize((new_w, new_h), Image.Resampling.BILINEAR)

    # Center crop to exact (target_w, target_h)
    crop_x = (new_w - target_w) // 2
    crop_y = (new_h - target_h) // 2
    im = im.crop((crop_x, crop_y, crop_x + target_w, crop_y + target_h))

    if is_cta:
        # Blur and darken for CTA closing scene
        im = im.filter(ImageFilter.GaussianBlur(radius=16))
        enhancer = ImageEnhance.Brightness(im)
        im = enhancer.enhance(0.55)

    _IMAGE_CACHE[cache_key] = im
    return im


def _get_scene_overlay(
    scene: PlannedScene,
    resolution: Tuple[int, int],
) -> Image.Image:
    """Retrieve or render cached RGBA overlay card."""
    cache_key = (scene.spec.id, resolution[0], resolution[1])
    if cache_key in _OVERLAY_CACHE:
        return _OVERLAY_CACHE[cache_key]

    overlay = render_scene_overlay(scene.spec, resolution)
    _OVERLAY_CACHE[cache_key] = overlay
    return overlay


def _render_single_scene_frame(
    scene: PlannedScene,
    t_scene: float,
    resolution: Tuple[int, int],
) -> Image.Image:
    """Render a single scene at time t_scene relative to scene start."""
    width, height = resolution
    is_cta = (scene.spec.kind == "cta")
    base_img = _get_base_image(scene.image_path, width, height, is_cta=is_cta)

    base_w, base_h = base_img.size
    max_dx = base_w - width
    max_dy = base_h - height

    # Normalized progress [0.0, 1.0] with smooth ease-in-out cosine curve
    p = max(0.0, min(1.0, t_scene / max(0.1, scene.duration)))
    ease_p = 0.5 - 0.5 * math.cos(math.pi * p)

    motion = scene.motion
    if motion == "zoom_in":
        # Scale from 1.0 to MARGIN_SCALE
        scale = 1.0 + (MARGIN_SCALE - 1.0) * ease_p
        window_w = int(base_w / scale)
        window_h = int(base_h / scale)
        cx, cy = base_w // 2, base_h // 2
        crop_box = (
            cx - window_w // 2,
            cy - window_h // 2,
            cx + window_w // 2,
            cy + window_h // 2,
        )
    elif motion == "zoom_out":
        # Scale from MARGIN_SCALE to 1.0
        scale = MARGIN_SCALE - (MARGIN_SCALE - 1.0) * ease_p
        window_w = int(base_w / scale)
        window_h = int(base_h / scale)
        cx, cy = base_w // 2, base_h // 2
        crop_box = (
            cx - window_w // 2,
            cy - window_h // 2,
            cx + window_w // 2,
            cy + window_h // 2,
        )
    elif motion == "pan_left":
        # Move crop window from right to left
        x0 = int(round(max_dx * (1.0 - ease_p)))
        y0 = max_dy // 2
        crop_box = (x0, y0, x0 + width, y0 + height)
    elif motion == "pan_right":
        # Move crop window from left to right
        x0 = int(round(max_dx * ease_p))
        y0 = max_dy // 2
        crop_box = (x0, y0, x0 + width, y0 + height)
    else:
        # Default center crop
        x0 = max_dx // 2
        y0 = max_dy // 2
        crop_box = (x0, y0, x0 + width, y0 + height)

    cropped = base_img.crop(crop_box)
    if cropped.size != (width, height):
        frame = cropped.resize((width, height), Image.Resampling.BILINEAR)
    else:
        frame = cropped

    # Calculate overlay alpha with smooth fade-in and fade-out
    alpha = 1.0
    if t_scene < OVERLAY_FADE_IN:
        alpha = t_scene / OVERLAY_FADE_IN
    elif t_scene > (scene.duration - OVERLAY_FADE_OUT):
        remaining = scene.duration - t_scene
        alpha = max(0.0, remaining / OVERLAY_FADE_OUT)

    if alpha > 0.01:
        overlay = _get_scene_overlay(scene, resolution)
        if alpha < 0.99:
            # Fast alpha scaling with LUT
            r, g, b, a = overlay.split()
            lut = [int(v * alpha) for v in range(256)]
            a = a.point(lut)
            overlay = Image.merge("RGBA", (r, g, b, a))

        frame = frame.copy()
        frame.paste(overlay, (0, 0), overlay)

    return frame


def render_frame(plan: VideoPlan, t: float) -> np.ndarray:
    """Stateless frame renderer: returns HxWx3 uint8 NumPy array at time t."""
    width, height = plan.resolution

    # Find active scene(s) at time t
    active_indices = []
    for i, s in enumerate(plan.scenes):
        if s.start <= t <= (s.start + s.duration):
            active_indices.append(i)

    if not active_indices:
        # If t is beyond duration, clamp to last scene
        if t >= plan.total_duration and plan.scenes:
            last_scene = plan.scenes[-1]
            frame = _render_single_scene_frame(
                last_scene, last_scene.duration, plan.resolution
            )
            return np.asarray(frame, dtype=np.uint8)
        # Blank black frame
        return np.zeros((height, width, 3), dtype=np.uint8)

    if len(active_indices) == 1:
        scene = plan.scenes[active_indices[0]]
        t_scene = t - scene.start
        frame = _render_single_scene_frame(scene, t_scene, plan.resolution)
        return np.asarray(frame, dtype=np.uint8)

    # Crossfade blending between two overlapping scenes
    idx_a, idx_b = active_indices[0], active_indices[1]
    scene_a = plan.scenes[idx_a]
    scene_b = plan.scenes[idx_b]

    frame_a = _render_single_scene_frame(scene_a, t - scene_a.start, plan.resolution)
    frame_b = _render_single_scene_frame(scene_b, t - scene_b.start, plan.resolution)

    # Crossfade progress alpha in [0.0, 1.0]
    overlap_start = scene_b.start
    alpha = max(0.0, min(1.0, (t - overlap_start) / CROSSFADE_DURATION))
    blended = Image.blend(frame_a, frame_b, alpha)
    return np.asarray(blended, dtype=np.uint8)


def clear_render_cache() -> None:
    """Clear memory caches for loaded images and overlay surfaces."""
    _IMAGE_CACHE.clear()
    _OVERLAY_CACHE.clear()

