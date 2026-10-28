"""Edge TTS voice synthesis backend using Microsoft neural voices.

Ultra-fast neural speech synthesis with zero local GPU/CPU model overhead.
Reduces video generation audio synthesis runtime from ~40s to ~2s.
"""

import asyncio
import hashlib
import io
import logging
import os
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np
import soundfile as sf

from propvid.config import get_settings
from propvid.errors import AudioError

logger = logging.getLogger(__name__)

DEFAULT_EDGE_VOICE = "en-IN-NeerjaNeural"

# Curated popular Edge TTS voices
EDGE_VOICES = {
    "indian_female": "en-IN-NeerjaNeural",
    "indian_male": "en-IN-PrabhatNeural",
    "us_female": "en-US-JennyNeural",
    "us_male": "en-US-GuyNeural",
    "us_aria": "en-US-AriaNeural",
    "uk_female": "en-GB-SoniaNeural",
    "uk_male": "en-GB-RyanNeural",
}


class TTSEdgeBackend:
    """High-speed neural TTS backend utilizing Edge TTS with disk caching."""

    def __init__(
        self,
        voice: Optional[str] = None,
        settings: Optional[Any] = None,
    ) -> None:
        self.settings = settings or get_settings()
        env_voice = os.getenv("PROPVID_EDGE_VOICE")
        self.voice = voice or env_voice or DEFAULT_EDGE_VOICE

        # Verify edge_tts is importable
        try:
            import edge_tts  # noqa: F401
        except ImportError as exc:
            raise AudioError(
                "edge-tts package is not installed. Install it with: pip install edge-tts"
            ) from exc

    async def _synth_async(self, text: str, rate: str) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice=self.voice, rate=rate)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        return audio_bytes

    def synth(self, text: str, direction: str = "warm") -> Tuple[np.ndarray, int]:
        """Synthesize text into a float32 mono audio array and sample rate."""
        if not text or not text.strip():
            return np.zeros(0, dtype=np.float32), 24000

        # Adjust pace slightly based on direction
        rate = "+4%" if direction == "excited" else "+0%"

        # Check disk cache
        cache_key = hashlib.sha256(f"{self.voice}:{rate}:{text}".encode("utf-8")).hexdigest()
        cache_file = self.settings.cache_dir / f"edge_{cache_key}.npy"

        if cache_file.exists():
            try:
                arr = np.load(cache_file)
                logger.info("Loaded cached Edge TTS speech clip (%s)", cache_file.name)
                return arr, 24000
            except Exception as exc:
                logger.warning("Failed to load Edge TTS cache %s: %s", cache_file, exc)

        try:
            # Run async synthesis
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        audio_bytes = executor.submit(
                            asyncio.run, self._synth_async(text, rate)
                        ).result()
                else:
                    audio_bytes = loop.run_until_complete(self._synth_async(text, rate))
            except RuntimeError:
                audio_bytes = asyncio.run(self._synth_async(text, rate))

            if not audio_bytes:
                raise AudioError("Edge TTS returned empty audio stream.")

            # Decode MP3 bytes directly with soundfile
            data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")

            # Convert stereo to mono if needed
            if data.ndim > 1:
                data = np.mean(data, axis=1)

            # Resample to 24000 Hz if necessary
            if sr != 24000:
                from propvid.audio.mix import resample_mono
                data = resample_mono(data, sr, 24000)
                sr = 24000

            # Save to disk cache
            try:
                self.settings.cache_dir.mkdir(parents=True, exist_ok=True)
                np.save(cache_file, data)
            except Exception as exc:
                logger.warning("Failed to write Edge TTS cache: %s", exc)

            return data, sr

        except Exception as exc:
            raise AudioError(f"Edge TTS synthesis failed for '{text[:30]}...': {exc}") from exc

    synthesize = synth
