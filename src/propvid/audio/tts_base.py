"""TTS protocol, backend resolution, and speech-only text normalization."""

import logging
import re
from typing import Any, Dict, Optional, Protocol, Tuple

import numpy as np

logger = logging.getLogger(__name__)

DIGIT_WORDS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}


def _expand_phone_digits(match: re.Match) -> str:
    """Expand phone number string into paced spoken digit words."""
    raw = match.group(0)
    has_plus = "+" in raw
    digits = [c for c in raw if c.isdigit()]

    if not digits:
        return raw

    # Group into country code and chunks of 5 digits
    words = []
    if has_plus:
        words.append("plus")

    # If starts with 91 and has 12 digits total
    if len(digits) == 12 and digits[:2] == ["9", "1"]:
        words.extend(["nine", "one,"])
        digits = digits[2:]

    # Group remaining digits in blocks of 5
    blocks = []
    chunk_size = 5 if len(digits) == 10 else len(digits)
    for i in range(0, len(digits), chunk_size):
        block_digits = [DIGIT_WORDS[d] for d in digits[i : i + chunk_size]]
        blocks.append(" ".join(block_digits))

    return (" ".join(words) + " " + ", ".join(blocks)).strip()


def normalize_for_speech(text: str) -> str:
    """Normalize text strictly for acoustic TTS rendering.

    Expands Indian Rupees, Crore/Lakh denominations, BHK designations,
    24x7 timing, and pacing for telephone numbers. Text overlays and facts
    verification remain unnormalized.
    """
    if not text:
        return ""

    out = text

    # 1. Price abbreviations: ₹1.25 Cr -> 1.25 crore rupees
    out = re.sub(
        r"₹\s*(\d+(?:[.,]\d+)*)\s*(?:cr|crore|crores)\b",
        r"\1 crore rupees",
        out,
        flags=re.IGNORECASE,
    )
    # ₹75 L -> 75 lakh rupees
    out = re.sub(
        r"₹\s*(\d+(?:[.,]\d+)*)\s*(?:l|lakh|lakhs)\b",
        r"\1 lakh rupees",
        out,
        flags=re.IGNORECASE,
    )
    # Remaining standalone ₹ -> rupees
    out = re.sub(r"₹\s*(\d+(?:[.,]\d+)*)", r"\1 rupees", out)

    # 2. BHK format: 2-BHK or 2 BHK -> 2 B H K
    out = re.sub(r"\b(\d+)\s*[-]?\s*bhk\b", r"\1 B H K", out, flags=re.IGNORECASE)

    # 3. 24x7 format -> twenty-four seven
    out = re.sub(r"\b24\s*[xX]\s*7\b", "twenty-four seven", out)

    # 4. Telephone numbers: e.g. +91 90000 00000
    phone_pattern = re.compile(r"(?:\+91[\s\-]*)?(?:[0-9][\s\-]*){10}")
    out = phone_pattern.sub(_expand_phone_digits, out)

    # Clean up double spaces
    out = re.sub(r"\s+", " ", out).strip()
    return out


class TTSBackend(Protocol):
    """Protocol for text-to-speech voice synthesis."""

    def synth(self, text: str, direction: str = "warm") -> Tuple[np.ndarray, int]:
        """Synthesize normalized text into float32 mono audio array and sample rate."""
        ...


class TTSNoneBackend:
    """Silent stub TTS backend returning empty audio."""

    def synth(self, text: str, direction: str = "warm") -> Tuple[np.ndarray, int]:
        return np.zeros(0, dtype=np.float32), 24000

    synthesize = synth


def get_backend(name: str = "auto", settings: Optional[Any] = None) -> TTSBackend:
    """Resolve and initialize requested TTS backend."""
    name_clean = (name or "auto").strip().lower()

    if name_clean == "none":
        return TTSNoneBackend()

    if name_clean == "kokoro":
        from propvid.audio.tts_kokoro import TTSKokoroBackend
        return TTSKokoroBackend(settings=settings) if settings else TTSKokoroBackend()

    if name_clean == "fish":
        from propvid.audio.tts_fish import TTSFishBackend
        return TTSFishBackend(settings=settings) if settings else TTSFishBackend()

    if name_clean == "auto":
        try:
            from propvid.audio.tts_kokoro import TTSKokoroBackend
            return TTSKokoroBackend(settings=settings) if settings else TTSKokoroBackend()
        except Exception:
            pass

        try:
            from propvid.audio.tts_fish import TTSFishBackend
            return TTSFishBackend(settings=settings) if settings else TTSFishBackend()
        except Exception:
            pass

        logger.warning(
            "No neural TTS backends available. Falling back to silent video mode."
        )
        return TTSNoneBackend()

    logger.warning("Unrecognized TTS backend '%s'. Falling back to silent mode.", name)
    return TTSNoneBackend()
