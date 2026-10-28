"""Configuration and settings management for propvid."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

# Load .env if present in workspace or parent
load_dotenv()

# Kokoro TTS Constants
DEFAULT_KOKORO_VOICE = "af_bella"
KOKORO_MODEL_FILENAME = "kokoro-v1.0.onnx"
KOKORO_VOICES_FILENAME = "voices-v1.0.bin"
KOKORO_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx"
KOKORO_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin"

# Available English Kokoro voices
KOKORO_VOICES = {
    "female": [
        "af_bella", "af_heart", "af_sarah", "af_alloy", "af_aoede",
        "af_jessica", "af_kore", "af_nicole", "af_nova", "af_river", "af_sky"
    ],
    "male": [
        "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
        "am_michael", "am_onyx", "am_puck", "am_santa"
    ]
}


@dataclass
class Settings:
    """Application settings and runtime defaults."""
    openrouter_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY") or None
    )
    openrouter_models: List[str] = field(
        default_factory=lambda: [
            m.strip()
            for m in os.getenv(
                "OPENROUTER_MODELS",
                "nvidia/nemotron-3.5-super-vl:free,google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
            ).split(",")
            if m.strip()
        ]
    )
    fish_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("FISH_API_KEY") or None
    )
    cache_dir: Path = field(
        default_factory=lambda: Path(os.getenv("PROPVID_CACHE_DIR", ".cache"))
    )
    models_dir: Path = field(
        default_factory=lambda: Path(os.getenv("PROPVID_MODELS_DIR", "models"))
    )
    assets_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent / "assets"
    )
    default_fps: int = 24
    default_resolution: tuple[int, int] = (1280, 720)
    default_tts_voice: str = DEFAULT_KOKORO_VOICE


def get_settings() -> Settings:
    """Return a fresh Settings instance."""
    return Settings()
