"""Audio mixing pipeline: speech placement, dynamic music ducking, and WAV export."""

from pathlib import Path
from typing import Dict, Optional, Tuple
import wave

import numpy as np

from propvid.schema import VideoPlan

MASTER_SAMPLE_RATE = 44100
SPEECH_START_OFFSET = 0.3      # seconds after scene start
MUSIC_GAIN_DUCKED = 0.12       # during narration
MUSIC_GAIN_STANDALONE = 0.25   # where there is no narration
PEAK_TARGET_DB = -1.0          # peak normalization target


def resample_mono(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample 1D float32 audio using high-quality linear interpolation."""
    if orig_sr == target_sr or len(audio) == 0:
        return audio
    duration = len(audio) / orig_sr
    new_len = int(round(duration * target_sr))
    orig_indices = np.linspace(0.0, len(audio) - 1, new_len, dtype=np.float32)
    return np.interp(orig_indices, np.arange(len(audio), dtype=np.float32), audio).astype(np.float32)


def mix_audio_track(
    plan: VideoPlan,
    narration_clips: Dict[str, Tuple[np.ndarray, int]],
    music_arr: Optional[np.ndarray],
    output_wav: Path,
    sample_rate: int = MASTER_SAMPLE_RATE,
) -> Path:
    """Mix per-scene speech narration clips with dynamic ducked background music.

    Places each narration clip at scene.start + 0.3s. Ducks music to gain 0.12
    when speech is active and 0.25 elsewhere. Peak-normalizes to -1.0 dB and
    writes standard 16-bit PCM WAV using stdlib wave.
    """
    output_wav = Path(output_wav).resolve()
    output_wav.parent.mkdir(parents=True, exist_ok=True)

    total_duration = plan.total_duration
    total_samples = max(1, int(round(total_duration * sample_rate)))

    narration_track = np.zeros(total_samples, dtype=np.float32)
    speech_mask = np.zeros(total_samples, dtype=np.float32)

    # 1. Place narration clips on timeline
    for scene in plan.scenes:
        if scene.spec.id in narration_clips:
            clip, clip_sr = narration_clips[scene.spec.id]
            if len(clip) > 0:
                resampled = resample_mono(clip, clip_sr, sample_rate)
                start_sample = int(round((scene.start + SPEECH_START_OFFSET) * sample_rate))
                end_sample = min(total_samples, start_sample + len(resampled))
                copy_len = end_sample - start_sample

                if copy_len > 0 and start_sample < total_samples:
                    narration_track[start_sample:end_sample] += resampled[:copy_len]
                    speech_mask[start_sample:end_sample] = 1.0

    # 2. Smooth speech mask for seamless ducking transitions (0.2s ramp)
    ramp_samples = int(round(0.2 * sample_rate))
    if ramp_samples > 0 and np.any(speech_mask > 0):
        kernel = np.ones(ramp_samples, dtype=np.float32) / ramp_samples
        # Convolve to smooth ducking envelope
        smoothed_mask = np.convolve(speech_mask, kernel, mode="same")
        ducking_envelope = (
            MUSIC_GAIN_STANDALONE - (MUSIC_GAIN_STANDALONE - MUSIC_GAIN_DUCKED) * np.clip(smoothed_mask, 0.0, 1.0)
        )
    else:
        ducking_envelope = np.full(total_samples, MUSIC_GAIN_STANDALONE, dtype=np.float32)

    # 3. Mix music track
    mixed = np.copy(narration_track)
    if music_arr is not None and len(music_arr) > 0:
        music_len = min(total_samples, len(music_arr))
        mixed[:music_len] += music_arr[:music_len] * ducking_envelope[:music_len]

    # 4. Peak normalize to -1.0 dB
    target_peak = 10.0 ** (PEAK_TARGET_DB / 20.0)  # ~0.891
    current_peak = float(np.max(np.abs(mixed)))
    if current_peak > 1e-4:
        mixed = mixed * (target_peak / current_peak)

    # 5. Convert to 16-bit PCM and export WAV
    pcm16 = np.clip(mixed * 32767.0, -32768.0, 32767.0).astype(np.int16)

    with wave.open(str(output_wav), "wb") as wf:
        wf.setnchannels(1)       # Mono
        wf.setsampwidth(2)       # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())

    return output_wav
