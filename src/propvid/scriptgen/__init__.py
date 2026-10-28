"""Script generation and verification package."""

from propvid.schema import PropertyInput, Script
from propvid.scriptgen.template import build_template_script


def generate_script(prop: PropertyInput) -> Script:
    """Generate deterministic script from property specification."""
    return build_template_script(prop)
