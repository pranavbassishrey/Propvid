"""Audio synthesis, text-to-speech, and audio mixing package."""

from propvid.audio.mix import mix_audio_track
from propvid.audio.music import synth_ambient
from propvid.audio.tts_base import get_backend, normalize_for_speech

__all__ = ["get_backend", "normalize_for_speech", "synth_ambient", "mix_audio_track"]
