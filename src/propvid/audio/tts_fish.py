"""Optional Fish Audio text-to-speech backend (Milestone 6)."""

import logging
from typing import Tuple

import numpy as np

from propvid.config import get_settings
from propvid.errors import AudioError

logger = logging.getLogger(__name__)


class TTSFishBackend:
    """Fish Audio API text-to-speech backend."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.fish_api_key:
            raise AudioError("FISH_API_KEY environment variable is not configured.")

    def synth(self, text: str, direction: str = "warm") -> Tuple[np.ndarray, int]:
        """Synthesize via Fish Audio endpoint (full API integration in Milestone 6)."""
        logger.warning("Fish Audio backend will be fully connected in Milestone 6.")
        return np.zeros(0, dtype=np.float32), 24000
