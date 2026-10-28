"""Tests for speech text normalization, music synthesis, and audio mixing."""

from pathlib import Path
import wave

import numpy as np
import pytest

from propvid.audio.mix import mix_audio_track, resample_mono
from propvid.audio.music import synth_ambient
from propvid.audio.tts_base import TTSNoneBackend, get_backend, normalize_for_speech
from propvid.inputs import ValidImage
from propvid.planner import plan_timeline
from propvid.schema import PropertyInput, SceneSpec, Script


def test_normalize_for_speech():
    """Verify acoustic text normalization for Indian real-estate conventions."""
    # 1. Price denominations (crores, lakhs, millions, billions, thousands with decimal point)
    assert "one point 25 crores" in normalize_for_speech("Offered at ₹1.25 Cr.")
    assert "one point 75 crores" in normalize_for_speech("Priced at 1.75cr.")
    assert "75 lakhs" in normalize_for_speech("Priced at ₹75 L.")
    assert "two point 5 millions" in normalize_for_speech("Valued at 2.5m.")
    assert "one point 2 billions" in normalize_for_speech("Project budget 1.2b.")
    assert "50 thousands" in normalize_for_speech("Booking token 50k.")

    # 2. BHK designation
    assert "2 B H K" in normalize_for_speech("A modern 2-BHK Apartment.")
    assert "3 B H K" in normalize_for_speech("Luxury 3 BHK Penthouse.")

    # 3. 24x7 timing
    assert "twenty-four seven" in normalize_for_speech("Features 24x7 security.")
    assert "twenty-four seven" in normalize_for_speech("Open 24X7.")

    # 4. Telephone numbers
    phone_spoken = normalize_for_speech("+91 90000 00000")
    assert "plus nine one" in phone_spoken
    assert "zero zero zero zero zero" in phone_spoken


def test_synth_ambient_music():
    """Verify procedural ambient soundtrack generation."""
    duration = 5.0
    sr = 44100
    music = synth_ambient(duration_seconds=duration, sample_rate=sr)

    assert isinstance(music, np.ndarray)
    assert music.dtype == np.float32
    assert len(music) == int(duration * sr)
    # Peak must be normalized safely
    assert float(np.max(np.abs(music))) <= 0.8
    # Last sample must fade out close to zero
    assert abs(float(music[-1])) < 0.05


def test_resample_mono():
    """Verify linear resampling preserves duration."""
    orig_sr = 24000
    target_sr = 44100
    # 1-second 440Hz sine wave at 24kHz
    t = np.linspace(0, 1.0, orig_sr, endpoint=False)
    sine_24k = np.sin(2 * np.pi * 440 * t).astype(np.float32)

    resampled = resample_mono(sine_24k, orig_sr, target_sr)
    assert len(resampled) == target_sr
    assert resampled.dtype == np.float32


def test_mix_audio_track(tmp_path: Path):
    """Verify mixing speech clips and ducked background music to WAV."""
    prop = PropertyInput(
        name="Audio Test Villa",
        location="Bengaluru",
        price="₹1 Cr",
        property_type="Villa",
    )
    img_path = tmp_path / "img.jpg"
    img_path.write_bytes(b"dummy")
    valid_images = [ValidImage(path=img_path, width=640, height=360)]

    scenes = [
        SceneSpec(
            id="s1",
            kind="title",
            headline="Title",
            caption="Cap",
            narration="Welcome to Audio Test Villa.",
        ),
        SceneSpec(
            id="s2",
            kind="cta",
            headline="CTA",
            caption="Cap",
            narration="Enquire today.",
        ),
    ]
    script = Script(scenes=scenes)
    plan, _ = plan_timeline(prop, script, valid_images)

    # Fake 2-second speech clip at 24kHz for scene s1
    clip_sr = 24000
    clip_samples = np.full(int(2.0 * clip_sr), 0.5, dtype=np.float32)
    narration_clips = {"s1": (clip_samples, clip_sr)}

    music = synth_ambient(plan.total_duration, sample_rate=44100)

    out_wav = tmp_path / "test_mix.wav"
    mix_audio_track(plan, narration_clips, music, out_wav, sample_rate=44100)

    assert out_wav.exists()
    assert out_wav.stat().st_size > 1000

    # Verify WAV header
    with wave.open(str(out_wav), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2  # 16-bit
        assert wf.getframerate() == 44100
        frames = wf.getnframes()
        assert frames == int(round(plan.total_duration * 44100))


def test_tts_none_backend():
    """Verify TTSNoneBackend returns zero-length audio."""
    backend = get_backend("none")
    assert isinstance(backend, TTSNoneBackend)
    arr, sr = backend.synth("Hello world")
    assert len(arr) == 0
    assert sr == 24000
