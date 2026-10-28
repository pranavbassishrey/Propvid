"""Output artifact generators: SRT subtitles, social share copy, and run report."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from propvid.schema import PropertyInput, Script, VideoPlan


def _format_srt_timestamp(seconds: float) -> str:
    """Format floating seconds as SRT timestamp: HH:MM:SS,mmm."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis = 0
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def write_srt(plan: VideoPlan, output_path: Path) -> Path:
    """Generate standard SubRip subtitle file (.srt) for the video timeline."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    for i, scene in enumerate(plan.scenes, start=1):
        # Slightly offset text appearance for readability within the scene
        sub_start = scene.start + 0.2
        sub_end = scene.start + scene.duration - 0.2
        start_str = _format_srt_timestamp(sub_start)
        end_str = _format_srt_timestamp(sub_end)

        text = scene.spec.caption or scene.spec.headline
        lines.append(f"{i}")
        lines.append(f"{start_str} --> {end_str}")
        lines.append(text)
        lines.append("")

    content = "\n".join(lines).strip() + "\n"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return output_path


def write_share_copy(prop: PropertyInput, script: Script, output_path: Path) -> Path:
    """Generate ready-to-share social media caption and hashtags without LLM calls."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Clean hashtags from location and property type
    loc_clean = re.sub(r"[^\w\s]", "", prop.location)
    loc_tokens = [f"#{t.capitalize()}" for t in loc_clean.split() if len(t) > 2]
    type_clean = re.sub(r"[^\w]", "", prop.property_type)

    hashtags = [
        f"#{type_clean}",
        *loc_tokens[:3],
        "#RealEstate",
        "#PropertyForSale",
        "#HomeTour",
    ]
    unique_hashtags = list(dict.fromkeys(hashtags))

    features_snippet = ""
    if prop.features:
        features_snippet = f" Highlights include {', '.join(prop.features[:3])}."

    contact_snippet = ""
    if prop.contact and (prop.contact.phone or prop.contact.email):
        contact_info = prop.contact.phone or prop.contact.email
        contact_snippet = f" Contact: {contact_info}."

    text = (
        f"Discover {prop.name} - {prop.property_type} in {prop.location} offered at {prop.price}."
        f"{features_snippet} {prop.cta}!{contact_snippet}\n\n"
        f"{' '.join(unique_hashtags)}\n"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

    return output_path


def write_report(
    input_facts: PropertyInput,
    output_path: Path,
    total_duration: float,
    llm_used: bool = False,
    models_requested: Optional[List[str]] = None,
    model_used: Optional[str] = None,
    cache_hit: bool = False,
    tokens: Optional[Dict[str, int]] = None,
    reverted_scenes: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    timings: Optional[Dict[str, float]] = None,
) -> Path:
    """Write comprehensive run_report.json documenting execution details."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Compute deterministic input facts hash
    facts_str = json.dumps(input_facts.model_dump(), sort_keys=True)
    input_hash = hashlib.sha256(facts_str.encode("utf-8")).hexdigest()[:16]

    # Inspect installed versions of core libraries
    package_versions = {}
    for pkg in ("pydantic", "pillow", "numpy", "imageio-ffmpeg", "httpx"):
        try:
            package_versions[pkg] = importlib.metadata.version(pkg)
        except Exception:
            package_versions[pkg] = "unknown"

    report_data = {
        "input_hash": input_hash,
        "property_name": input_facts.name,
        "total_duration_seconds": round(total_duration, 2),
        "llm_used": llm_used,
        "models_requested": models_requested or [],
        "model_used": model_used or ("none (template)" if not llm_used else "unknown"),
        "cache_hit": cache_hit,
        "tokens": tokens or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "reverted_scenes": reverted_scenes or [],
        "warnings": warnings or [],
        "timings": timings or {},
        "package_versions": package_versions,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    return output_path
