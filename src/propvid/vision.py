"""Two-step image classification and scene-to-image matching for propvid.

Step 1: Fast deterministic keyword classification based on filenames & labels
        (e.g., '12_kitchen.jpg', 'bathroom.png', 'frontal.jpg', 'living_room.jpg').
Step 2: Vision-LLM fallback via OpenRouter for randomly/generically named images
        (e.g., 'IMG_0042.jpg', 'dsc_1020.jpg').
"""

import base64
import hashlib
import io
import json
import logging
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple

import httpx
from PIL import Image

from propvid.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Canonical room/scene categories
CATEGORY_KITCHEN = "kitchen"
CATEGORY_BATHROOM = "bathroom"
CATEGORY_BEDROOM = "bedroom"
CATEGORY_LIVING = "living_room"
CATEGORY_DINING = "dining_room"
CATEGORY_EXTERIOR = "exterior"
CATEGORY_POOL = "pool"
CATEGORY_PARKING = "parking"
CATEGORY_BALCONY = "balcony"
CATEGORY_GYM = "gym"
CATEGORY_UNKNOWN = "general"

ALL_CATEGORIES = [
    CATEGORY_KITCHEN,
    CATEGORY_BATHROOM,
    CATEGORY_BEDROOM,
    CATEGORY_LIVING,
    CATEGORY_DINING,
    CATEGORY_EXTERIOR,
    CATEGORY_POOL,
    CATEGORY_PARKING,
    CATEGORY_BALCONY,
    CATEGORY_GYM,
]

# Keywords for Step 1 (Filename / Label Matching)
FILENAME_KEYWORDS: Dict[str, List[str]] = {
    CATEGORY_KITCHEN: [
        "kitchen", "modular_kitchen", "pantry", "cook", "culinary", "chef"
    ],
    CATEGORY_BATHROOM: [
        "bathroom", "washroom", "restroom", "toilet", "bath", "powder_room", "shower"
    ],
    CATEGORY_BEDROOM: [
        "bedroom", "bed", "master_bed", "guest_bed", "suite"
    ],
    CATEGORY_DINING: [
        "dining", "fine_dining", "dinner", "banquet", "breakfast"
    ],
    CATEGORY_LIVING: [
        "living", "hall", "lounge", "drawing", "salon", "indoor", "interior", "family_room"
    ],
    CATEGORY_POOL: [
        "pool", "swimming", "aquatic", "jacuzzi"
    ],
    CATEGORY_PARKING: [
        "parking", "garage", "carport", "driveway"
    ],
    CATEGORY_BALCONY: [
        "balcony", "terrace", "deck", "patio", "rooftop", "veranda"
    ],
    CATEGORY_GYM: [
        "gym", "fitness", "workout", "sports", "clubhouse"
    ],
    CATEGORY_EXTERIOR: [
        "frontal", "exterior", "elevation", "front", "outdoor", "facade", "building", "entrance", "aerial", "view"
    ],
}

# Categories strictly incompatible with each other (never show bathroom for kitchen/dining, etc.)
INCOMPATIBLE_CATEGORIES: Dict[str, Set[str]] = {
    CATEGORY_KITCHEN: {CATEGORY_BATHROOM, CATEGORY_BEDROOM},
    CATEGORY_DINING: {CATEGORY_BATHROOM, CATEGORY_BEDROOM},
    CATEGORY_BATHROOM: {CATEGORY_KITCHEN, CATEGORY_DINING, CATEGORY_LIVING, CATEGORY_EXTERIOR},
    CATEGORY_BEDROOM: {CATEGORY_KITCHEN, CATEGORY_BATHROOM},
}


CATEGORY_PRECEDENCE = [
    CATEGORY_POOL,
    CATEGORY_GYM,
    CATEGORY_PARKING,
    CATEGORY_BALCONY,
    CATEGORY_BATHROOM,
    CATEGORY_KITCHEN,
    CATEGORY_DINING,
    CATEGORY_BEDROOM,
    CATEGORY_EXTERIOR,
    CATEGORY_LIVING,
]


def classify_by_filename(path_or_name: Path | str) -> Optional[str]:
    """Step 1: Classify image based on filename stem and keywords.

    Splits filename into tokens using underscores, dashes, and digits.
    Returns canonical category if a match is found, or None.
    """
    stem = Path(path_or_name).stem.lower()
    # Normalize separators: e.g. 12_bathroom -> "12 bathroom", living-room -> "living room"
    tokens = re.sub(r"[_\-\d]+", " ", stem).strip()
    words = set(tokens.split())

    # Check in strict precedence order (e.g. pool checked before general indoor/living)
    for cat in CATEGORY_PRECEDENCE:
        keywords = FILENAME_KEYWORDS.get(cat, [])
        for kw in keywords:
            if kw in words or kw in stem:
                return cat

    return None


def _get_image_thumbnail_base64(image_path: Path, max_size: int = 512) -> Tuple[str, str]:
    """Downscale image for fast LLM vision transmission and compute sha256 hash."""
    with Image.open(image_path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=80)
        img_bytes = buf.getvalue()

    img_hash = hashlib.sha256(img_bytes).hexdigest()
    b64_str = base64.b64encode(img_bytes).decode("ascii")
    return f"data:image/jpeg;base64,{b64_str}", img_hash


def classify_with_vision_llm(
    image_path: Path, settings: Optional[Settings] = None
) -> Optional[str]:
    """Step 2: Classify random/unlabelled image via OpenRouter vision model.

    Results are cached on disk by image hash to avoid repeat API calls.
    """
    if settings is None:
        settings = get_settings()

    api_key = settings.openrouter_api_key
    if not api_key:
        return None

    try:
        data_uri, img_hash = _get_image_thumbnail_base64(image_path)
    except Exception as exc:
        logger.warning("Failed to prepare thumbnail for %s: %s", image_path, exc)
        return None

    # Check disk cache
    cache_file = settings.cache_dir / f"vision_{img_hash[:16]}.json"
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            cat = cached.get("category")
            if cat in ALL_CATEGORIES:
                logger.info("Vision cache hit for %s -> %s", image_path.name, cat)
                return cat
        except Exception:
            pass

    # Request OpenRouter vision completion
    models = settings.openrouter_models[:3]
    prompt = (
        "Classify this real estate listing photograph into exactly ONE category from this list: "
        f"{json.dumps(ALL_CATEGORIES)}. "
        'Respond ONLY with a JSON object: {"category": "<one_category_from_list>"}'
    )

    req_body = {
        "model": models[0] if models else "nvidia/nemotron-3.5-super-vl:free",
        "models": models,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 250,
        "reasoning": {"max_tokens": 0},
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/pbsmarta/propvid",
        "X-Title": "propvid",
    }

    try:
        with httpx.Client(timeout=25.0) as client:
            resp = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=req_body,
            )
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    return None
                msg = choices[0].get("message") or {}
                raw_text = msg.get("content") or msg.get("reasoning") or ""
                if not raw_text or not isinstance(raw_text, str):
                    return None

                # Tolerant JSON parsing
                m = re.search(r"\{.*?\}", raw_text, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
                    cat = str(parsed.get("category", "")).strip().lower()
                    if cat in ALL_CATEGORIES:
                        settings.cache_dir.mkdir(parents=True, exist_ok=True)
                        cache_file.write_text(json.dumps({"category": cat}), encoding="utf-8")
                        logger.info("Vision API classified %s -> %s", image_path.name, cat)
                        return cat

                # Fallback: check if any canonical category name appears in the text
                lowered = raw_text.lower()
                for candidate in ALL_CATEGORIES:
                    if candidate in lowered:
                        settings.cache_dir.mkdir(parents=True, exist_ok=True)
                        cache_file.write_text(json.dumps({"category": candidate}), encoding="utf-8")
                        logger.info("Vision API extracted category %s -> %s", image_path.name, candidate)
                        return candidate
    except Exception as exc:
        logger.warning("Vision LLM classification failed for %s: %s", image_path.name, exc)

    return None


def classify_image(image_path: Path, settings: Optional[Settings] = None) -> str:
    """Classify image using Step 1 (filename/label) followed by Step 2 (Vision LLM)."""
    # Step 1: Filename check
    cat = classify_by_filename(image_path)
    if cat:
        return cat

    # Step 2: Vision LLM fallback
    cat = classify_with_vision_llm(image_path, settings=settings)
    if cat:
        return cat

    return CATEGORY_UNKNOWN


def extract_scene_target_category(scene) -> Optional[str]:
    """Detect which room/feature category a scene refers to based on its text."""
    text = f"{scene.headline} {scene.caption} {scene.narration}".lower()

    if any(k in text for k in ["kitchen", "modular kitchen", "culinary", "pantry", "cooking"]):
        return CATEGORY_KITCHEN
    if any(k in text for k in ["bathroom", "washroom", "restroom", "bath", "shower", "powder room"]):
        return CATEGORY_BATHROOM
    if any(k in text for k in ["bedroom", "bed", "master suite"]):
        return CATEGORY_BEDROOM
    if any(k in text for k in ["dining", "fine-dining", "dinner", "feast"]):
        return CATEGORY_DINING
    if any(k in text for k in ["pool", "swimming", "aquatic"]):
        return CATEGORY_POOL
    if any(k in text for k in ["parking", "garage", "covered parking", "vehicle"]):
        return CATEGORY_PARKING
    if any(k in text for k in ["balcony", "terrace", "deck", "patio", "view"]):
        return CATEGORY_BALCONY
    if any(k in text for k in ["gym", "fitness", "workout"]):
        return CATEGORY_GYM
    if any(k in text for k in ["living", "hall", "lounge", "drawing", "spacious"]):
        return CATEGORY_LIVING

    return None


def match_scenes_to_images(
    scenes: list,
    valid_images: list,
    settings: Optional[Settings] = None,
) -> List[Tuple[object, Path, int]]:
    """Match scenes to images with strict content-to-photo alignment.

    Ensures that a washroom photo is NEVER shown during a kitchen voiceover,
    and assigns exterior shots to Title/CTA.

    Returns:
        List of tuples: (scene, assigned_image_path, assigned_image_index)
    """
    if not valid_images:
        return []

    # 1. Classify all images
    img_classifications: List[str] = [
        classify_image(img.path, settings=settings) for img in valid_images
    ]
    logger.info("Image classifications: %s", [f"{img.path.name}:{c}" for img, c in zip(valid_images, img_classifications)])

    used_indices: Set[int] = set()
    matches: List[Tuple[object, Path, int]] = []

    # Find candidate indices by category
    def find_indices_for_category(cat: str, allow_used: bool = False) -> List[int]:
        res = [i for i, c in enumerate(img_classifications) if c == cat]
        if not allow_used:
            res = [i for i in res if i not in used_indices]
        return res

    for i, scene in enumerate(scenes):
        chosen_idx: Optional[int] = None

        if scene.kind == "title":
            # If first image is acceptable (exterior, living room, or not bathroom/kitchen)
            if img_classifications[0] not in (CATEGORY_BATHROOM, CATEGORY_KITCHEN):
                chosen_idx = 0
            else:
                candidates = find_indices_for_category(CATEGORY_EXTERIOR) or find_indices_for_category(CATEGORY_LIVING)
                chosen_idx = candidates[0] if candidates else 0

        elif scene.kind == "cta":
            # Last image is conventional closing shot, provided it is not a bathroom
            last_idx = len(valid_images) - 1
            if img_classifications[last_idx] != CATEGORY_BATHROOM:
                chosen_idx = last_idx
            else:
                candidates = find_indices_for_category(CATEGORY_EXTERIOR) or find_indices_for_category(CATEGORY_LIVING)
                chosen_idx = candidates[0] if candidates else last_idx

        else:
            # 1. Check if an image has an explicit user-defined feature tag matching this scene
            for idx, img in enumerate(valid_images):
                if idx not in used_indices and getattr(img, "feature", None):
                    feat_str = str(img.feature).strip().lower()
                    if feat_str in scene.headline.lower() or feat_str in scene.caption.lower():
                        chosen_idx = idx
                        break

            # 2. Match target category (e.g. kitchen -> kitchen photo)
            if chosen_idx is None:
                target_cat = extract_scene_target_category(scene)
                if target_cat:
                    candidates = find_indices_for_category(target_cat)
                    if not candidates:
                        candidates = find_indices_for_category(target_cat, allow_used=True)
                    if candidates:
                        chosen_idx = candidates[0]

            # If no direct category match, find an unused image that is NOT incompatible
            if chosen_idx is None:
                incompatible = set(INCOMPATIBLE_CATEGORIES.get(target_cat, set()))
                # Bathrooms should NEVER be picked for a feature unless that feature is a bathroom
                if target_cat != CATEGORY_BATHROOM:
                    incompatible.add(CATEGORY_BATHROOM)

                unused = [
                    idx for idx in range(len(valid_images))
                    if idx not in used_indices and img_classifications[idx] not in incompatible
                ]
                if unused:
                    chosen_idx = unused[0]
                else:
                    # Allow reusing already used non-incompatible images before ever using an incompatible one
                    compatible_all = [
                        idx for idx in range(len(valid_images))
                        if img_classifications[idx] not in incompatible
                    ]
                    if compatible_all:
                        chosen_idx = compatible_all[i % len(compatible_all)]
                    else:
                        chosen_idx = i % len(valid_images)

        used_indices.add(chosen_idx)
        matches.append((scene, valid_images[chosen_idx].path, chosen_idx))

    return matches
