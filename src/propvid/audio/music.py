"""Procedural ambient music synthesis and audio file loading."""

import math
from pathlib import Path
import subprocess
from typing import List, Tuple

import imageio_ffmpeg
import numpy as np

from propvid.errors import AudioError

# 4-chord progression frequencies (Hz): Cmaj7 -> Am7 -> Fmaj7 -> G9
CHORD_PROGRESSION = [
    [130.81, 164.81, 196.00, 246.94],  # C3, E3, G3, B3
    [110.00, 130.81, 164.81, 196.00],  # A2, C3, E3, G3
    [87.31, 110.00, 130.81, 164.81],   # F2, A2, C3, E3
    [98.00, 123.47, 146.83, 174.61],   # G2, B2, D3, F3
]
CHORD_DURATION = 4.0  # seconds per chord loop step


def synth_ambient(
    duration_seconds: float,
    sample_rate: int = 44100,
    seed: int = 42,
) -> np.ndarray:
    """Generate a lush, royalty-free procedural ambient soundtrack using pure NumPy.

    Features a slow 4-chord progression, soft harmonic overtones, warm chorus detuning,
    gentle attack/release envelopes, and an overall 2-second fade-out.
    """
    total_samples = int(round(duration_seconds * sample_rate))
    if total_samples <= 0:
        return np.zeros(0, dtype=np.float32)

    t = np.arange(total_samples, dtype=np.float32) / sample_rate
    audio = np.zeros(total_samples, dtype=np.float32)

    chord_samples = int(round(CHORD_DURATION * sample_rate))
    num_chords = len(CHORD_PROGRESSION)

    # Attack and release envelopes per chord
    attack_samples = int(round(0.8 * sample_rate))
    release_samples = int(round(0.8 * sample_rate))

    env_attack = np.linspace(0.0, 1.0, attack_samples, dtype=np.float32)
    env_release = np.linspace(1.0, 0.0, release_samples, dtype=np.float32)

    # Synthesize chord by chord
    current_idx = 0
    chord_counter = 0

    while current_idx < total_samples:
        seg_len = min(chord_samples, total_samples - current_idx)
        seg_t = t[current_idx : current_idx + seg_len]
        chord_freqs = CHORD_PROGRESSION[chord_counter % num_chords]

        seg_audio = np.zeros(seg_len, dtype=np.float32)

        for freq in chord_freqs:
            # Fundamental + chorus detune (+/- 0.3 Hz)
            f1 = 2.0 * math.pi * freq
            f_chorus = 2.0 * math.pi * (freq + 0.35)
            # Gentle 2nd harmonic
            f2 = 2.0 * math.pi * (freq * 2.0)

            tone = (
                0.60 * np.sin(f1 * seg_t)
                + 0.35 * np.sin(f_chorus * seg_t)
                + 0.15 * np.sin(f2 * seg_t)
            )
            seg_audio += tone

        # Apply chord envelope
        envelope = np.ones(seg_len, dtype=np.float32)
        if seg_len >= attack_samples:
            envelope[:attack_samples] = env_attack
        if seg_len >= release_samples:
            envelope[-release_samples:] *= env_release

        audio[current_idx : current_idx + seg_len] += seg_audio * envelope
        current_idx += chord_samples
        chord_counter += 1

    # Overall track fade out over the last 2.0 seconds
    fade_out_samples = int(round(min(2.0, duration_seconds) * sample_rate))
    if fade_out_samples > 0:
        fade_env = np.linspace(1.0, 0.0, fade_out_samples, dtype=np.float32)
        audio[-fade_out_samples:] *= fade_env

    # Soft peak normalization
    peak = float(np.max(np.abs(audio)))
    if peak > 1e-4:
        audio = (audio / peak) * 0.75

    return audio.astype(np.float32)


def load_audio_file(path: Path, target_sample_rate: int = 44100) -> np.ndarray:
    """Decode any audio file to float32 mono array via FFmpeg."""
    file_path = Path(path).resolve()
    if not file_path.exists():
        raise AudioError(f"Audio file not found: {file_path}")

    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(file_path),
        "-ac", "1",
        "-ar", str(target_sample_rate),
        "-f", "s16le",
        "-",
    ]

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        raw_bytes = proc.stdout
        arr_int16 = np.frombuffer(raw_bytes, dtype=np.int16)
        arr_float = arr_int16.astype(np.float32) / 32768.0
        return arr_float
    except Exception as exc:
        raise AudioError(f"Failed to decode audio file {file_path}: {exc}") from exc
