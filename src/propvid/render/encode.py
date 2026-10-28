"""FFmpeg video encoding and raw frame streaming."""

import collections
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Callable, Optional

import imageio_ffmpeg

from propvid.errors import RenderError
from propvid.render.frames import clear_render_cache, render_frame
from propvid.schema import VideoPlan

logger = logging.getLogger(__name__)


def encode_video(
    plan: VideoPlan,
    output_path: Path,
    audio_path: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Path:
    """Encode video by streaming raw RGB24 frames into FFmpeg via stdin pipe.

    Uses libx264, yuv420p, preset veryfast, crf 23, faststart.
    Writes to a temporary file in output_path.parent then renames atomically.
    Raises RenderError with the last 20 lines of FFmpeg stderr on failure.
    """
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clear_render_cache()

    width, height = plan.resolution
    fps = plan.fps
    total_duration = plan.total_duration
    total_frames = max(1, int(round(total_duration * fps)))

    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()

    # Build FFmpeg command arguments
    cmd = [
        ffmpeg_bin,
        "-y",
        "-nostats",
        "-loglevel", "warning",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{width}x{height}",
        "-pix_fmt", "rgb24",
        "-r", str(fps),
        "-i", "-",  # Video input from stdin
    ]

    if audio_path and Path(audio_path).exists():
        cmd.extend([
            "-i", str(audio_path),
            "-c:a", "aac",
            "-b:a", "160k",
            "-shortest",
        ])
    else:
        # Silent video output
        cmd.extend(["-an"])

    temp_out = output_path.with_name(f".{output_path.name}.tmp.mp4")

    cmd.extend([
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "veryfast",
        "-crf", "23",
        "-movflags", "+faststart",
        str(temp_out),
    ])

    stderr_lines = collections.deque(maxlen=25)

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except Exception as exc:
        raise RenderError(f"Failed to start FFmpeg process: {exc}") from exc

    # Stream frames into FFmpeg stdin
    last_reported_pct = -1
    dt = 1.0 / fps

    try:
        assert proc.stdin is not None
        for frame_idx in range(total_frames):
            t = frame_idx * dt
            frame_arr = render_frame(plan, t)
            proc.stdin.write(frame_arr.tobytes())

            pct = int((frame_idx + 1) * 100 / total_frames)
            if pct % 10 == 0 and pct != last_reported_pct:
                sys.stderr.write(f"\r[INFO] Encoding video: {pct}% ({frame_idx + 1}/{total_frames} frames)")
                sys.stderr.flush()
                last_reported_pct = pct

            if progress_callback:
                progress_callback(frame_idx + 1, total_frames)

        proc.stdin.close()
        sys.stderr.write("\n")
        sys.stderr.flush()

    except (BrokenPipeError, IOError) as exc:
        # FFmpeg process crashed early or stdin closed
        if proc.poll() is None:
            proc.kill()
        stderr_output = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        tail = "\n".join(stderr_output.splitlines()[-20:])
        raise RenderError(f"FFmpeg pipe broken during encoding:\n{tail}") from exc

    # Wait for completion and capture stderr
    stderr_bytes = proc.stderr.read() if proc.stderr else b""
    retcode = proc.wait()

    if retcode != 0:
        err_msg = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else "Unknown error"
        tail = "\n".join(err_msg.splitlines()[-20:])
        if temp_out.exists():
            temp_out.unlink()
        raise RenderError(f"FFmpeg encoding failed with exit code {retcode}:\n{tail}")

    # Atomic rename to destination
    if temp_out.exists():
        temp_out.rename(output_path)
    else:
        raise RenderError(f"FFmpeg did not produce output file at {temp_out}")

    clear_render_cache()
    return output_path
