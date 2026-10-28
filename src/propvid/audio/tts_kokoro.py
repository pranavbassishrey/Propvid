"""Kokoro ONNX text-to-speech synthesis backend."""

import logging
import os
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np

from propvid.config import (
    DEFAULT_KOKORO_VOICE,
    KOKORO_MODEL_FILENAME,
    KOKORO_VOICES_FILENAME,
    get_settings,
)
from propvid.errors import AudioError

logger = logging.getLogger(__name__)


class TTSKokoroBackend:
    """Offline neural TTS engine using Kokoro ONNX runtime."""

    def __init__(
        self,
        model_path: Optional[Path] = None,
        voices_path: Optional[Path] = None,
        voice: str = DEFAULT_KOKORO_VOICE,
        settings: Optional[Any] = None,
    ) -> None:
        self.voice = voice
        settings = settings or get_settings()

        env_model = os.getenv("PROPVID_KOKORO_MODEL")
        env_voices = os.getenv("PROPVID_KOKORO_VOICES")

        self.model_path = Path(env_model) if env_model else (model_path or (settings.models_dir / KOKORO_MODEL_FILENAME))
        self.voices_path = Path(env_voices) if env_voices else (voices_path or (settings.models_dir / KOKORO_VOICES_FILENAME))

        if not self.model_path.exists() or not self.voices_path.exists():
            raise AudioError(
                f"Kokoro model files missing in {settings.models_dir}. "
                f"Run 'python scripts/download_tts_models.py' to download them."
            )

        try:
            from kokoro_onnx import Kokoro
            self._kokoro = Kokoro(str(self.model_path), str(self.voices_path))
        except Exception as exc:
            raise AudioError(f"Failed to initialize Kokoro ONNX model: {exc}") from exc

    def synth(self, text: str, direction: str = "warm") -> Tuple[np.ndarray, int]:
        """Synthesize normalized text to audio array."""
        if not text or not text.strip():
            return np.zeros(0, dtype=np.float32), 24000

        # Adjust pace slightly based on scene direction
        speed = 1.0
        if direction == "excited":
            speed = 1.05
        elif direction == "calm":
            speed = 0.95

        try:
            samples, sample_rate = self._kokoro.create(
                text,
                voice=self.voice,
                speed=speed,
                lang="en-us",
            )
            return np.asarray(samples, dtype=np.float32), sample_rate
        except Exception as exc:
            logger.warning("Kokoro synthesis failed for text '%s': %s", text, exc)
            raise AudioError(f"Kokoro synthesis failed: {exc}") from exc

    synthesize = synth
