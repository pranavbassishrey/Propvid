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


NUM_WORDS = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
    16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen",
    20: "twenty", 30: "thirty", 40: "forty", 50: "fifty",
    60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety",
}

UNIT_SPEECH_MAP = {
    "cr": "crores",
    "crore": "crores",
    "crores": "crores",
    "l": "lakhs",
    "lac": "lakhs",
    "lacs": "lakhs",
    "lakh": "lakhs",
    "lakhs": "lakhs",
    "m": "millions",
    "million": "millions",
    "millions": "millions",
    "b": "billions",
    "billion": "billions",
    "billions": "billions",
    "k": "thousands",
    "thousand": "thousands",
    "thousands": "thousands",
}


def _int_to_words(n: int) -> str:
    """Convert integer up to 999 to English words for natural pronunciation."""
    if n in NUM_WORDS:
        return NUM_WORDS[n]
    if n < 100:
        tens = (n // 10) * 10
        rem = n % 10
        return f"{NUM_WORDS[tens]}-{NUM_WORDS[rem]}"
    if n < 1000:
        hundreds = n // 100
        rem = n % 100
        res = f"{NUM_WORDS[hundreds]} hundred"
        if rem:
            res += f" {_int_to_words(rem)}"
        return res
    return str(n)


def _format_price_speech(match: re.Match) -> str:
    """Format price for natural voiceover delivery.

    e.g. 1.75cr -> 'one point 75 crores', 75l -> '75 lakhs', 2.5m -> 'two point 5 millions'.
    Decimals are pronounced 'point' with non-spaced digits.
    """
    int_str, dec_str, unit_raw = match.groups()
    val_int = int(int_str)
    unit = UNIT_SPEECH_MAP.get(unit_raw.lower(), unit_raw.lower())

    if dec_str:
        spoken_num = f"{_int_to_words(val_int)} point {dec_str}"
    else:
        spoken_num = _int_to_words(val_int) if val_int < 20 else str(val_int)

    return f"{spoken_num} {unit}"


def normalize_for_speech(text: str) -> str:
    """Normalize text strictly for acoustic TTS rendering.

    Expands prices (e.g. 1.75cr -> one point 75 crores, 75L -> 75 lakhs),
    BHK designations (5BHK -> 5 B H K), 24x7 timing, and telephone pacing.
    Text overlays and facts verification remain unnormalized.
    """
    if not text:
        return ""

    out = text

    # 1. Price normalizations (with or without currency symbol)
    price_pattern = re.compile(
        r"(?:(?:₹|rs\.?|inr|\$)\s*)?(\d+)(?:\.(\d+))?\s*(cr|crores?|lakhs?|lacs?|l|millions?|m|billions?|b|thousands?|k)\b",
        re.IGNORECASE,
    )
    out = price_pattern.sub(_format_price_speech, out)

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

    if name_clean in ("edge", "edge-tts", "edgetts"):
        from propvid.audio.tts_edge import TTSEdgeBackend
        return TTSEdgeBackend(settings=settings) if settings else TTSEdgeBackend()

    if name_clean == "fish":
        from propvid.audio.tts_fish import TTSFishBackend
        return TTSFishBackend(settings=settings) if settings else TTSFishBackend()

    if name_clean == "auto":
        # Prefer kokoro if models are present locally
        try:
            from propvid.audio.tts_kokoro import TTSKokoroBackend
            return TTSKokoroBackend(settings=settings) if settings else TTSKokoroBackend()
        except Exception:
            pass

        # Fall back to edge-tts if installed
        try:
            from propvid.audio.tts_edge import TTSEdgeBackend
            return TTSEdgeBackend(settings=settings) if settings else TTSEdgeBackend()
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
