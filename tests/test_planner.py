"""Tests for timeline planner and output generation."""

import json
from pathlib import Path

from propvid.inputs import check_images, load_property
from propvid.outputs import write_report, write_share_copy, write_srt
from propvid.planner import CROSSFADE_OVERLAP, plan_timeline
from propvid.scriptgen.template import build_template_script


def test_planner_full_sample_duration_bounds():
    """Verify standard sample plans a video timeline between 20s and 40s."""
    prop, base_dir = load_property("examples/property.sample.json")
    valid_images = check_images(prop.images, base_dir)
    script = build_template_script(prop)

    plan, warnings = plan_timeline(prop, script, valid_images)

    assert 20.0 <= plan.total_duration <= 40.0
    assert len(plan.scenes) == len(script.scenes)

    # Check crossfade overlap continuity
    for i in range(1, len(plan.scenes)):
        prev = plan.scenes[i - 1]
        curr = plan.scenes[i]
        expected_start = prev.start + prev.duration - CROSSFADE_OVERLAP
        assert abs(curr.start - expected_start) < 1e-4


def test_planner_short_timeline_extends_title_and_cta():
    """Verify minimal scenes raise duration to 4.5s and extend title/CTA hold times."""
    prop, base_dir = load_property("examples/property.minimal.json")
    valid_images = check_images(prop.images, base_dir)
    script = build_template_script(prop)

    plan, warnings = plan_timeline(prop, script, valid_images)

    # Title + 1 highlight + CTA = 3 scenes
    assert len(plan.scenes) == 3
    # Check that minimum duration was raised above 3.5s
    assert plan.scenes[1].duration >= 4.5
    # Check that Title and CTA hold times were extended
    assert plan.scenes[0].duration > 4.5
    assert plan.scenes[-1].duration > 4.5
    # Total duration should be close to or bounded near 20s
    assert plan.total_duration >= 18.0


def test_planner_drops_trailing_scenes_if_over_40s():
    """Verify scenes are dropped to prevent total duration from exceeding 40s."""
    prop, base_dir = load_property("examples/property.sample.json")
    valid_images = check_images(prop.images, base_dir)
    script = build_template_script(prop)

    # Artificially force very long durations (7.0s per scene)
    artificial_durations = {s.id: 15.0 for s in script.scenes}
    plan, warnings = plan_timeline(
        prop, script, valid_images, narration_durations=artificial_durations
    )

    assert plan.total_duration <= 40.0
    # Title and CTA must always remain
    assert plan.scenes[0].spec.kind == "title"
    assert plan.scenes[-1].spec.kind == "cta"
    assert any("Dropped trailing feature scene" in w for w in warnings)


def test_planner_image_assignment_and_motion():
    """Verify image assignment rules and motion preset cycling on reuse."""
    prop, base_dir = load_property("examples/property.sample.json")
    valid_images = check_images(prop.images, base_dir)
    script = build_template_script(prop)

    plan, _ = plan_timeline(prop, script, valid_images)

    # Title uses first image
    assert plan.scenes[0].image_path == valid_images[0].path
    # CTA uses last image
    assert plan.scenes[-1].image_path == valid_images[-1].path

    # All scenes must have a valid motion preset
    valid_motions = {"zoom_in", "zoom_out", "pan_left", "pan_right"}
    for scene in plan.scenes:
        assert scene.motion in valid_motions


def test_output_artifacts(tmp_path: Path):
    """Verify writing SRT, share copy, and run_report.json."""
    prop, base_dir = load_property("examples/property.sample.json")
    valid_images = check_images(prop.images, base_dir)
    script = build_template_script(prop)
    plan, warnings = plan_timeline(prop, script, valid_images)

    # 1. SRT output
    srt_file = tmp_path / "captions.srt"
    write_srt(plan, srt_file)
    assert srt_file.exists()
    srt_content = srt_file.read_text(encoding="utf-8")
    assert "-->" in srt_content
    assert "1" in srt_content
    assert prop.name in srt_content or "Bengaluru" in srt_content

    # 2. Share copy output
    share_file = tmp_path / "share_copy.txt"
    write_share_copy(prop, script, share_file)
    assert share_file.exists()
    share_content = share_file.read_text(encoding="utf-8")
    assert prop.name in share_content
    assert "#" in share_content
    assert prop.price in share_content

    # 3. Report output
    report_file = tmp_path / "run_report.json"
    write_report(
        input_facts=prop,
        output_path=report_file,
        total_duration=plan.total_duration,
        llm_used=False,
    )
    assert report_file.exists()
    report_data = json.loads(report_file.read_text(encoding="utf-8"))
    assert report_data["property_name"] == prop.name
    assert report_data["llm_used"] is False
    assert "input_hash" in report_data
    assert "pydantic" in report_data["package_versions"]
