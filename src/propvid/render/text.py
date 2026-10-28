"""Font loading, glyph verification, and text layout utilities."""

from pathlib import Path
from typing import Optional, Union

from PIL import ImageFont

from propvid.config import get_settings


def font_has_glyph(font: ImageFont.FreeTypeFont, char: str = "₹") -> bool:
    """Verify whether a TrueType font contains an actual glyph for the given character.

    Compares the rendered mask against a known non-existent codepoint (\U0010FFFF)
    to differentiate real glyph geometry from missing-glyph (.notdef) fallback boxes.
    """
    try:
        mask_char = font.getmask(char)
        if mask_char.getbbox() is None:
            return False
        mask_missing = font.getmask("\U0010FFFF")
        # If the font lacks the character, it will render identical mask data to the fallback
        return bytes(mask_char) != bytes(mask_missing)
    except Exception:
        return False


def load_font(
    size: int,
    bold: bool = False,
    font_path: Optional[Union[Path, str]] = None,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font from assets/fonts or specified path with fallback to Pillow default."""
    settings = get_settings()
    fonts_dir = settings.assets_dir / "fonts"

    candidates = []
    if font_path:
        candidates.append(Path(font_path))
    else:
        if bold:
            candidates.extend([
                fonts_dir / "DejaVuSans-Bold.ttf",
                fonts_dir / "NotoSans-Bold.ttf",
            ])
        candidates.extend([
            fonts_dir / "DejaVuSans.ttf",
            fonts_dir / "NotoSans-Regular.ttf",
        ])

    for p in candidates:
        if p.exists():
            try:
                font = ImageFont.truetype(str(p), size)
                return font
            except Exception:
                continue

    # Fallback to default PIL font
    return ImageFont.load_default()
