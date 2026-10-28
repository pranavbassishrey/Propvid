"""Download Kokoro ONNX model and voices files."""

import os
from pathlib import Path
import sys
import urllib.request

from propvid.config import (
    KOKORO_MODEL_FILENAME,
    KOKORO_MODEL_URL,
    KOKORO_VOICES_FILENAME,
    KOKORO_VOICES_URL,
    get_settings,
)


def download_file(url: str, dest_path: Path) -> None:
    """Download a file with progress reporting."""
    if dest_path.exists():
        print(f"[OK] Already exists: {dest_path}")
        return

    print(f"Downloading {url} -> {dest_path}...")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(".tmp")

    def report_hook(count, block_size, total_size):
        if total_size > 0:
            percent = int(count * block_size * 100 / total_size)
            sys.stdout.write(f"\r  Progress: {percent}% ({count * block_size // (1024*1024)} MB / {total_size // (1024*1024)} MB)")
            sys.stdout.flush()

    try:
        urllib.request.urlretrieve(url, temp_path, reporthook=report_hook)
        print()
        temp_path.rename(dest_path)
        print(f"[OK] Completed: {dest_path}")
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink()
        print(f"\n[ERROR] Failed to download {url}: {exc}", file=sys.stderr)
        raise


def main() -> None:
    settings = get_settings()
    models_dir = settings.models_dir
    models_dir.mkdir(parents=True, exist_ok=True)

    download_file(KOKORO_MODEL_URL, models_dir / KOKORO_MODEL_FILENAME)
    download_file(KOKORO_VOICES_URL, models_dir / KOKORO_VOICES_FILENAME)
    print("\nKokoro ONNX model assets ready in", models_dir)


if __name__ == "__main__":
    main()
