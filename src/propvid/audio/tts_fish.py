"""Fish Audio cloud TTS synthesis backend with disk caching."""

import hashlib
import io
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

import httpx
import numpy as np

from propvid.config import Settings, get_settings
from propvid.errors import AudioError

logger = logging.getLogger(__name__)

FISH_TTS_URL = "https://api.fish.audio/v1/tts"


class TTSFishBackend:
    """Cloud neural TTS backend using Fish Audio API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        reference_id: Optional[str] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.api_key = api_key or self.settings.fish_api_key or os.getenv("FISH_API_KEY")
        self.reference_id = reference_id or os.getenv("FISH_VOICE_ID")

        if not self.api_key:
            raise AudioError("FISH_API_KEY environment variable is not configured.")

    def synth(self, text: str, direction: str = "warm") -> Tuple[np.ndarray, int]:
        """Synthesize normalized text using Fish Audio API."""
        if not text or not text.strip():
            return np.zeros(0, dtype=np.float32), 24000

        # Deterministic cache lookup
        cache_key_raw = f"{text}||{self.reference_id or 'default'}||fish"
        cache_hash = hashlib.sha256(cache_key_raw.encode("utf-8")).hexdigest()
        cache_file = self.settings.cache_dir / f"fish_{cache_hash}.npy"

        if cache_file.exists():
            try:
                data = np.load(cache_file)
                sr = 44100
                logger.info("Loaded cached Fish audio: %s", cache_file.name)
                return data, sr
            except Exception as exc:
                logger.warning("Failed to load cached audio %s: %s", cache_file, exc)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "format": "wav",
        }
        if self.reference_id:
            payload["reference_id"] = self.reference_id

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(FISH_TTS_URL, headers=headers, json=payload)

            if resp.status_code != 200:
                err_msg = f"Fish Audio API returned HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning(err_msg)
                raise AudioError(err_msg)

            # Decode audio using soundfile
            import soundfile as sf
            audio_arr, sr = sf.read(io.BytesIO(resp.content), dtype="float32")

            # Convert multi-channel to mono if necessary
            if audio_arr.ndim > 1:
                audio_arr = np.mean(audio_arr, axis=1)

            # Persist to disk cache
            try:
                self.settings.cache_dir.mkdir(parents=True, exist_ok=True)
                np.save(cache_file, audio_arr)
            except Exception as exc:
                logger.warning("Failed to write Fish audio cache %s: %s", cache_file, exc)

            return audio_arr, int(sr)

        except Exception as exc:
            if isinstance(exc, AudioError):
                raise
            raise AudioError(f"Fish Audio synthesis connection error: {exc}") from exc
