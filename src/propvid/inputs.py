"""Input loading, validation, and image pre-checking for propvid."""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageOps
from pydantic import ValidationError

from propvid.errors import InputError
from propvid.schema import ImageRef, PropertyInput

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("name", "location", "price", "property_type")
MIN_IMAGE_WIDTH = 640
MIN_IMAGE_HEIGHT = 360


@dataclass
class ValidImage:
    """Pre-verified and sanitized image reference."""
    path: Path
    feature: Optional[str] = None
    label: Optional[str] = None
    width: int = 0
    height: int = 0


def load_property(path: Path | str) -> Tuple[PropertyInput, Path]:
    """Load and validate a property JSON file.

    Collects all missing required fields and raises a single clear InputError
    if any are missing. Resolves relative image paths against the JSON file's parent dir.

    Returns:
        Tuple of (validated PropertyInput, base_dir Path)
    """
    file_path = Path(path).resolve()
    if not file_path.exists():
        raise InputError(f"Input file not found: {file_path}")
    if not file_path.is_file():
        raise InputError(f"Input path is not a file: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except json.JSONDecodeError as exc:
        raise InputError(f"Invalid JSON in {file_path}: {exc.msg} (line {exc.lineno}, col {exc.colno})") from exc
    except Exception as exc:
        raise InputError(f"Failed to read input file {file_path}: {exc}") from exc

    if not isinstance(raw_data, dict):
        raise InputError(f"Root JSON element must be an object/dict in {file_path}")

    # Check for all required fields first to provide a single comprehensive error message
    missing_fields = [
        field
        for field in REQUIRED_FIELDS
        if not str(raw_data.get(field) or "").strip()
    ]
    if missing_fields:
        fields_str = ", ".join(f"'{f}'" for f in missing_fields)
        raise InputError(f"Missing required property field(s): {fields_str}")

    base_dir = file_path.parent

    try:
        prop = PropertyInput.model_validate(raw_data)
    except ValidationError as exc:
        err_messages = [f"{err['loc']}: {err['msg']}" for err in exc.errors()]
        raise InputError(f"Schema validation error(s):\n" + "\n".join(err_messages)) from exc

    # Resolve image paths relative to JSON file location
    resolved_images: List[ImageRef] = []
    for img in prop.images:
        p = Path(img.path)
        resolved_path = p if p.is_absolute() else (base_dir / p).resolve()
        resolved_images.append(
            ImageRef(path=str(resolved_path), feature=img.feature, label=img.label)
        )
    prop.images = resolved_images

    return prop, base_dir


def check_images(images: List[ImageRef], base_dir: Path) -> List[ValidImage]:
    """Validate image accessibility, integrity, orientation, and minimum dimensions.

    Skips missing, unreadable, or undersized images with logged warnings.
    Raises InputError if zero valid images are available.
    Warns if fewer than 4 valid images are found.
    """
    valid_images: List[ValidImage] = []

    for img in images:
        img_path = Path(img.path)
        if not img_path.is_absolute():
            img_path = (base_dir / img_path).resolve()

        if not img_path.exists():
            logger.warning("Image file does not exist, skipping: %s", img_path)
            continue

        try:
            with Image.open(img_path) as im:
                # Apply EXIF rotation to ensure correct orientation
                im = ImageOps.exif_transpose(im)
                w, h = im.size
                if w < MIN_IMAGE_WIDTH or h < MIN_IMAGE_HEIGHT:
                    logger.warning(
                        "Image is smaller than minimum required %dx%d (got %dx%d), skipping: %s",
                        MIN_IMAGE_WIDTH,
                        MIN_IMAGE_HEIGHT,
                        w,
                        h,
                        img_path,
                    )
                    continue

                valid_images.append(
                    ValidImage(
                        path=img_path,
                        feature=img.feature,
                        label=img.label,
                        width=w,
                        height=h,
                    )
                )
        except Exception as exc:
            logger.warning("Corrupted or unreadable image file, skipping %s: %s", img_path, exc)
            continue

    if not valid_images:
        raise InputError(
            f"Zero valid images found. At least one readable image (>= {MIN_IMAGE_WIDTH}x{MIN_IMAGE_HEIGHT}) is required."
        )

    if len(valid_images) < 4:
        logger.warning(
            "Found only %d valid image(s) (recommended: 4-8). Existing images will be reused across scenes with varied motion.",
            len(valid_images),
        )

    return valid_images
