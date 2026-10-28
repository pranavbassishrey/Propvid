"""Font loading, text layout, and RGBA overlay drawing for video scenes."""

from pathlib import Path
from typing import List, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont

from propvid.config import get_settings
from propvid.schema import SceneSpec


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
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue

    return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_width: int) -> List[str]:
    """Wrap text into lines that fit within max_width pixels."""
    words = text.split()
    if not words:
        return []

    lines: List[str] = []
    current_line = words[0]

    for word in words[1:]:
        test_line = f"{current_line} {word}"
        try:
            bbox = font.getbbox(test_line)
            w = bbox[2] - bbox[0]
        except Exception:
            w = len(test_line) * 10

        if w <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word

    lines.append(current_line)
    return lines


def render_scene_overlay(
    spec: SceneSpec,
    resolution: Tuple[int, int] = (1280, 720),
) -> Image.Image:
    """Generate a high-contrast RGBA overlay image for a given scene.

    Uses semi-transparent dark backing panels and verified typography
    to ensure crisp readability over any background image.
    """
    width, height = resolution
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Scaling factor for fonts and padding based on resolution (relative to 720p)
    scale = height / 720.0
    accent_gold = (212, 175, 55, 255)
    text_white = (255, 255, 255, 255)
    text_sub = (220, 225, 235, 240)
    panel_bg = (12, 18, 28, 220)  # semi-transparent dark navy/black
    border_color = (212, 175, 55, 180)

    if spec.kind == "title":
        # Centered Luxury Opening Card
        font_title = load_font(int(42 * scale), bold=True)
        font_sub = load_font(int(24 * scale), bold=False)

        card_w = int(width * 0.75)
        card_h = int(190 * scale)
        x0 = (width - card_w) // 2
        y0 = (height - card_h) // 2

        # Rounded dark panel with gold border
        draw.rounded_rectangle(
            [x0, y0, x0 + card_w, y0 + card_h],
            radius=int(14 * scale),
            fill=panel_bg,
            outline=border_color,
            width=int(2 * scale),
        )

        # Headline (Property Name)
        headline_wrapped = wrap_text(spec.headline, font_title, card_w - int(80 * scale))
        headline_text = headline_wrapped[0] if headline_wrapped else spec.headline
        bbox_head = font_title.getbbox(headline_text)
        head_w = bbox_head[2] - bbox_head[0]
        draw.text(
            (x0 + (card_w - head_w) // 2, y0 + int(35 * scale)),
            headline_text,
            font=font_title,
            fill=text_white,
        )

        # Gold decorative horizontal rule
        rule_w = int(200 * scale)
        rule_x = x0 + (card_w - rule_w) // 2
        rule_y = y0 + int(100 * scale)
        draw.line([(rule_x, rule_y), (rule_x + rule_w, rule_y)], fill=accent_gold, width=int(2 * scale))

        # Caption (Location • Price)
        bbox_sub = font_sub.getbbox(spec.caption)
        sub_w = bbox_sub[2] - bbox_sub[0]
        draw.text(
            (x0 + (card_w - sub_w) // 2, y0 + int(120 * scale)),
            spec.caption,
            font=font_sub,
            fill=accent_gold,
        )

    elif spec.kind in ("feature", "highlight"):
        # Lower-third informational overlay panel
        font_head = load_font(int(32 * scale), bold=True)
        font_cap = load_font(int(20 * scale), bold=False)

        margin_left = int(60 * scale)
        margin_bottom = int(60 * scale)
        panel_w = int(width * 0.65)
        panel_h = int(130 * scale)
        x0 = margin_left
        y0 = height - margin_bottom - panel_h

        # Panel with rounded right corners / subtle border
        draw.rounded_rectangle(
            [x0, y0, x0 + panel_w, y0 + panel_h],
            radius=int(10 * scale),
            fill=panel_bg,
            outline=border_color,
            width=int(2 * scale),
        )

        # Tag label
        tag_text = "FEATURE HIGHLIGHT" if spec.kind == "feature" else "PROPERTY HIGHLIGHT"
        font_tag = load_font(int(14 * scale), bold=True)
        draw.text((x0 + int(30 * scale), y0 + int(20 * scale)), tag_text, font=font_tag, fill=accent_gold)

        # Headline
        draw.text(
            (x0 + int(30 * scale), y0 + int(48 * scale)),
            spec.headline,
            font=font_head,
            fill=text_white,
        )

        # Subtitle caption
        draw.text(
            (x0 + int(30 * scale), y0 + int(90 * scale)),
            spec.caption,
            font=font_cap,
            fill=text_sub,
        )

    elif spec.kind == "cta":
        # Centered CTA enquiry card
        font_cta = load_font(int(38 * scale), bold=True)
        font_contact = load_font(int(24 * scale), bold=False)

        card_w = int(width * 0.80)
        card_h = int(220 * scale)
        x0 = (width - card_w) // 2
        y0 = (height - card_h) // 2

        draw.rounded_rectangle(
            [x0, y0, x0 + card_w, y0 + card_h],
            radius=int(16 * scale),
            fill=panel_bg,
            outline=accent_gold,
            width=int(3 * scale),
        )

        # Headline
        bbox_cta = font_cta.getbbox(spec.headline)
        cta_w = bbox_cta[2] - bbox_cta[0]
        draw.text(
            (x0 + (card_w - cta_w) // 2, y0 + int(40 * scale)),
            spec.headline,
            font=font_cta,
            fill=accent_gold,
        )

        # Divider line
        rule_w = int(320 * scale)
        rule_x = x0 + (card_w - rule_w) // 2
        rule_y = y0 + int(105 * scale)
        draw.line([(rule_x, rule_y), (rule_x + rule_w, rule_y)], fill=(255, 255, 255, 120), width=int(2 * scale))

        # Contact Details
        contact_text = spec.caption if spec.caption != spec.headline else "Contact your sales advisor today"
        bbox_con = font_contact.getbbox(contact_text)
        con_w = bbox_con[2] - bbox_con[0]
        draw.text(
            (x0 + (card_w - con_w) // 2, y0 + int(130 * scale)),
            contact_text,
            font=font_contact,
            fill=text_white,
        )

    return overlay
