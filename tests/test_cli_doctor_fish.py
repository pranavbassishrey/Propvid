"""Unit tests for doctor health check, init command, and Fish Audio backend."""

import argparse
import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import wave

import numpy as np
import pytest

from propvid.audio.tts_fish import TTSFishBackend
from propvid.cli import cmd_doctor, cmd_init
from propvid.config import Settings
from propvid.errors import AudioError
from propvid.inputs import check_images, load_property


def test_doctor_command_passes():
    args = argparse.Namespace(ping=False)
    exit_code = cmd_doctor(args)
    assert exit_code == 0


def test_init_command_creates_valid_property(tmp_path):
    target = tmp_path / "test_property.json"
    args = argparse.Namespace(out=target, defaults=True)
    exit_code = cmd_init(args)
    assert exit_code == 0
    assert target.exists()

    prop, base_dir = load_property(target)
    assert prop.name == "Green Valley Heights"
    assert prop.location == "Whitefield, Bengaluru"
    assert prop.price == "₹1.25 Cr"
    assert len(prop.images) > 0


def test_fish_audio_no_key_raises(tmp_path):
    settings = Settings(fish_api_key=None, cache_dir=tmp_path / "cache")
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(AudioError, match="FISH_API_KEY"):
            TTSFishBackend(api_key=None, settings=settings)


def _generate_mock_wav_bytes(num_samples: int = 1000, sample_rate: int = 44100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        pcm_data = (np.sin(np.linspace(0, 10, num_samples)) * 16000).astype(np.int16)
        wf.writeframes(pcm_data.tobytes())
    return buf.getvalue()


def test_fish_audio_mock_synthesis_and_caching(tmp_path):
    cache_dir = tmp_path / "cache"
    settings = Settings(fish_api_key="test_fish_key", cache_dir=cache_dir)
    backend = TTSFishBackend(api_key="test_fish_key", settings=settings)

    wav_bytes = _generate_mock_wav_bytes()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = wav_bytes

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        arr, sr = backend.synth("Welcome to the luxury home.")
        assert mock_post.call_count == 1
        assert len(arr) > 0
        assert sr == 44100

    # Ensure disk cache was written
    cached_files = list(cache_dir.glob("fish_*.npy"))
    assert len(cached_files) == 1

    # Second call should hit cache without network call
    with patch("httpx.Client.post") as mock_post2:
        arr2, sr2 = backend.synth("Welcome to the luxury home.")
        assert mock_post2.call_count == 0
        assert np.array_equal(arr, arr2)
