"""LLM-based script polish with OpenRouter, caching, and per-scene fact verification."""

from dataclasses import dataclass, field
import hashlib
import json
import logging
import re
import time
from typing import Dict, List, Optional, Tuple

import httpx

from propvid.config import Settings, get_settings
from propvid.schema import PropertyInput, SceneSpec, Script
from propvid.scriptgen.verify import verify_scene

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert real estate video copywriter.
Your task is to polish video narration to sound natural, rhythmic, and conversational when spoken aloud.

CRITICAL RULES:
1. FACT INTEGRITY: Use ONLY facts explicitly provided. NEVER invent amenities, claims, numbers, distances, or ratings.
2. NO PUFFERY: Do not use banned hype phrases like "best", "cheapest", "guaranteed", "number one", "#1", "walking distance", "minutes from", "rera".
3. STRUCTURE: Keep the exact same scene IDs, scene kinds, and scene order. Return the exact same number of scenes.
4. LENGTH LIMITS:
   - headline: max 6 words (<= 32 characters)
   - caption: max 8 words (or 12 words for CTA) (<= 50 characters)
   - narration: max 20 words (<= 120 characters)
5. OUTPUT FORMAT: Respond ONLY with a valid JSON object matching:
{
  "scenes": [
    {
      "id": "scene_id",
      "kind": "title|feature|highlight|cta",
      "headline": "Short punchy headline",
      "caption": "Brief onscreen caption",
      "narration": "Natural, spoken voiceover narration"
    }
  ]
}
Do NOT include any markdown, code blocks, preambles, or explanations outside the JSON object."""


@dataclass
class LLMReport:
    """Execution report for LLM polish step."""
    llm_used: bool = False
    model_used: Optional[str] = None
    models_requested: List[str] = field(default_factory=list)
    cache_hit: bool = False
    tokens: Dict[str, int] = field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    reverted_scenes: List[str] = field(default_factory=list)
    latency_sec: float = 0.0
    error: Optional[str] = None


def _parse_llm_json(raw_text: Optional[str]) -> Optional[dict]:
    """Parse JSON tolerantly from LLM completion text."""
    if not raw_text or not isinstance(raw_text, str):
        return None
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        json_str = text[start : end + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    return None


def polish_script_with_llm(
    prop: PropertyInput,
    template_script: Script,
    settings: Optional[Settings] = None,
) -> Tuple[Script, LLMReport]:
    """Polish template script narration using OpenRouter with fallback and verification.

    If network, parsing, or API failures occur, returns the template script safely.
    Each scene returned by the LLM is audited by verify_scene; any failing scene
    reverts to its template counterpart.
    """
    if settings is None:
        settings = get_settings()

    api_key = settings.openrouter_api_key
    # OpenRouter requires 'models' array to have 3 items or fewer
    models = settings.openrouter_models[:3]
    if not api_key:
        return template_script, LLMReport(
            llm_used=False,
            models_requested=models,
            error="No OpenRouter API key provided",
        )

    facts_dict = {
        "name": prop.name,
        "location": prop.location,
        "price": prop.price,
        "property_type": prop.property_type,
        "tone": prop.tone,
        "features": prop.features,
        "cta": prop.cta,
    }
    if prop.contact:
        facts_dict["contact"] = {
            "name": prop.contact.name,
            "phone": prop.contact.phone,
            "email": prop.contact.email,
        }

    template_scenes_data = [
        {
            "id": s.id,
            "kind": s.kind,
            "headline": s.headline,
            "caption": s.caption,
            "narration": s.narration,
        }
        for s in template_script.scenes
    ]

    user_prompt = (
        f"Property facts:\n{json.dumps(facts_dict, indent=2)}\n\n"
        f"Template script scenes to polish:\n{json.dumps(template_scenes_data, indent=2)}\n\n"
        "Please polish the headline, caption, and narration for natural voiceover delivery "
        "while strictly adhering to all facts, scene IDs, kinds, and constraints."
    )

    # Compute deterministic cache key
    cache_prompt_ver = "v1"
    cache_payload = (
        json.dumps(facts_dict, sort_keys=True)
        + "||"
        + ",".join(models)
        + "||"
        + cache_prompt_ver
    )
    cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()
    cache_file = settings.cache_dir / f"{cache_key}.json"

    raw_completion: Optional[str] = None
    model_used: Optional[str] = None
    tokens: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    cache_hit = False
    latency_sec = 0.0

    # 1. Check disk cache
    if cache_file.exists():
        try:
            cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
            raw_completion = cached_data.get("content")
            model_used = cached_data.get("model", models[0] if models else "openrouter")
            tokens = cached_data.get("usage", tokens)
            cache_hit = True
            logger.info("Loaded cached LLM response (%s)", cache_file.name)
        except Exception as exc:
            logger.warning("Failed to read cache file %s: %s", cache_file, exc)

    # 2. Make network request if not cached
    if raw_completion is None:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/pbsmarta/propvid",
            "X-Title": "propvid",
        }
        req_body = {
            "model": models[0] if models else "nvidia/nemotron-3.5-super-vl:free",
            "models": models,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 800,
            "reasoning": {"max_tokens": 0},
        }

        req_start = time.time()
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=req_body,
                )
            latency_sec = round(time.time() - req_start, 2)
            if resp.status_code != 200:
                err_msg = f"OpenRouter API returned HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning(err_msg)
                return template_script, LLMReport(
                    llm_used=False,
                    models_requested=models,
                    latency_sec=latency_sec,
                    error=err_msg,
                )

            data = resp.json()
            model_used = data.get("model", models[0] if models else "openrouter")
            usage_raw = data.get("usage", {})
            tokens = {
                "prompt_tokens": int(usage_raw.get("prompt_tokens", 0)),
                "completion_tokens": int(usage_raw.get("completion_tokens", 0)),
                "total_tokens": int(usage_raw.get("total_tokens", 0)),
            }
            choices = data.get("choices", [])
            if not choices:
                err_msg = "OpenRouter response contained no choices"
                logger.warning(err_msg)
                return template_script, LLMReport(
                    llm_used=False,
                    models_requested=models,
                    latency_sec=latency_sec,
                    error=err_msg,
                )

            raw_completion = choices[0].get("message", {}).get("content")

            # Persist to cache only if valid completion was received
            if raw_completion and isinstance(raw_completion, str) and raw_completion.strip():
                try:
                    settings.cache_dir.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(
                        json.dumps(
                            {
                                "model": model_used,
                                "content": raw_completion,
                                "usage": tokens,
                            },
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                except Exception as exc:
                    logger.warning("Failed to write LLM cache %s: %s", cache_file, exc)

        except Exception as exc:
            latency_sec = round(time.time() - req_start, 2)
            err_msg = f"Network or connection error during LLM request: {exc}"
            logger.warning(err_msg)
            return template_script, LLMReport(
                llm_used=False,
                models_requested=models,
                latency_sec=latency_sec,
                error=err_msg,
            )

    # 3. Parse JSON completion
    parsed_json = _parse_llm_json(raw_completion)
    if not parsed_json or "scenes" not in parsed_json or not isinstance(parsed_json["scenes"], list):
        logger.warning(
            "Could not parse valid scenes JSON from LLM response. Content snippet: %s",
            raw_completion[:150],
        )
        return template_script, LLMReport(
            llm_used=False,
            model_used=model_used,
            models_requested=models,
            cache_hit=cache_hit,
            tokens=tokens,
            latency_sec=latency_sec,
            error="Malformed JSON response from LLM",
        )

    # Map candidate scenes by id
    candidate_map = {}
    for item in parsed_json["scenes"]:
        if isinstance(item, dict) and "id" in item:
            candidate_map[str(item["id"])] = item

    # 4. Verify each scene and revert if invalid
    final_scenes: List[SceneSpec] = []
    reverted_scenes: List[str] = []

    for idx, tmpl in enumerate(template_script.scenes):
        cand_dict = candidate_map.get(tmpl.id)
        if not cand_dict and idx < len(parsed_json["scenes"]):
            # Fallback by index if LLM omitted or changed ID
            cand_dict = parsed_json["scenes"][idx]

        if not cand_dict or not isinstance(cand_dict, dict):
            final_scenes.append(tmpl)
            reverted_scenes.append(tmpl.id)
            continue

        cand_scene = SceneSpec(
            id=tmpl.id,
            kind=tmpl.kind,
            headline=str(cand_dict.get("headline", tmpl.headline)).strip() or tmpl.headline,
            caption=str(cand_dict.get("caption", tmpl.caption)).strip() or tmpl.caption,
            narration=str(cand_dict.get("narration", tmpl.narration)).strip() or tmpl.narration,
            direction=tmpl.direction,
        )

        violations = verify_scene(cand_scene, prop)
        if violations:
            logger.warning(
                "Fact verification violation in LLM scene '%s': %s. Reverting to template.",
                tmpl.id,
                violations,
            )
            final_scenes.append(tmpl)
            reverted_scenes.append(tmpl.id)
        else:
            final_scenes.append(cand_scene)

    return Script(scenes=final_scenes), LLMReport(
        llm_used=True,
        model_used=model_used,
        models_requested=models,
        cache_hit=cache_hit,
        tokens=tokens,
        reverted_scenes=reverted_scenes,
        latency_sec=latency_sec,
    )
