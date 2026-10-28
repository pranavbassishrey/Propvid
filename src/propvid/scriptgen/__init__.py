"""Script generation, LLM polish, and fact verification package."""

from typing import Optional, Tuple

from propvid.config import Settings, get_settings
from propvid.schema import PropertyInput, Script
from propvid.scriptgen.llm import LLMReport, polish_script_with_llm
from propvid.scriptgen.template import build_template_script


def generate_script(
    prop: PropertyInput,
    llm_mode: str = "auto",
    settings: Optional[Settings] = None,
) -> Tuple[Script, LLMReport]:
    """Generate script from property specification with optional LLM polish.

    Modes:
      - 'off': Deterministic template script only (no LLM calls).
      - 'auto': Use LLM polish if OPENROUTER_API_KEY is configured, else fallback.
      - 'on': Request LLM polish.
    """
    template_script = build_template_script(prop)
    if llm_mode == "off":
        return template_script, LLMReport(llm_used=False)

    if settings is None:
        settings = get_settings()

    if not settings.openrouter_api_key:
        if llm_mode == "on":
            import logging
            logging.getLogger(__name__).warning("OPENROUTER_API_KEY not found; cannot polish script.")
        return template_script, LLMReport(
            llm_used=False,
            models_requested=settings.openrouter_models,
            error="OPENROUTER_API_KEY not configured",
        )

    return polish_script_with_llm(prop, template_script, settings=settings)
