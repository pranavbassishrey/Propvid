"""Smoke test for fast rendering at 320x180 producing a valid MP4."""

from pathlib import Path
import subprocess

import imageio_ffmpeg
from PIL import Image

from propvid.inputs import ValidImage
from propvid.planner import plan_timeline
from propvid.render.encode import encode_video
from propvid.schema import PropertyInput, SceneSpec, Script


def test_smoke_render_320x180(tmp_path: Path):
    """Smoke test: render 2-scene 320x180 video to verify FFmpeg pipeline."""
    # 1. Create two tiny valid images
    img1_path = tmp_path / "img1.jpg"
    img2_path = tmp_path / "img2.jpg"
    Image.new("RGB", (640, 360), color=(30, 60, 90)).save(img1_path)
    Image.new("RGB", (640, 360), color=(90, 60, 30)).save(img2_path)

    prop = PropertyInput(
        name="Smoke Test Villa",
        location="Bengaluru",
        price="₹1 Cr",
        property_type="Villa",
    )
    valid_images = [
        ValidImage(path=img1_path, width=640, height=360),
        ValidImage(path=img2_path, width=640, height=360),
    ]

    scenes = [
        SceneSpec(
            id="s1",
            kind="title",
            headline="Smoke Test Villa",
            caption="Bengaluru • ₹1 Cr",
            narration="Welcome to Smoke Test Villa in Bengaluru.",
        ),
        SceneSpec(
            id="s2",
            kind="cta",
            headline="Enquire today",
            caption="Contact sales team",
            narration="Enquire today for details.",
        ),
    ]
    script = Script(scenes=scenes, source="template")

    # Fast plan: 320x180 at 12 fps
    plan, _ = plan_timeline(
        prop,
        script,
        valid_images,
        resolution=(320, 180),
        fps=12,
    )

    out_mp4 = tmp_path / "smoke.mp4"
    encode_video(plan, out_mp4)

    assert out_mp4.exists()
    assert out_mp4.stat().st_size > 10_000  # greater than 10KB

    # Verify video validity using ffmpeg probe
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    res = subprocess.run(
        [ffmpeg_exe, "-v", "error", "-i", str(out_mp4), "-f", "null", "-"],
        capture_output=True,
    )
    assert res.returncode == 0
