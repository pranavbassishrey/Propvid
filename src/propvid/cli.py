"""Command-line interface for propvid."""

import argparse
import logging
from pathlib import Path
import sys
import traceback
from typing import Optional, Sequence

from propvid.errors import InputError, PropvidError, RenderError
from propvid.inputs import check_images, load_property

# Reconfigure stdout/stderr to UTF-8 with replacement for Windows console safety
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("propvid")


def setup_logging(debug: bool = False) -> None:
    """Configure logging format and log levels."""
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a property JSON file and its referenced images."""
    prop, base_dir = load_property(args.input)
    valid_images = check_images(prop.images, base_dir)

    print("[OK] Property data and media validation succeeded:")
    print(f"  - Name:          {prop.name}")
    print(f"  - Location:      {prop.location}")
    print(f"  - Price:         {prop.price}")
    print(f"  - Type:          {prop.property_type}")
    print(f"  - Tone:          {prop.tone}")
    print(f"  - Features:      {len(prop.features)} feature(s)")
    for f in prop.features:
        print(f"      - {f}")
    print(f"  - Images:        {len(valid_images)} valid image(s) verified (from {len(prop.images)} declared)")
    if prop.contact:
        contact_parts = [
            part
            for part in [prop.contact.name, prop.contact.phone, prop.contact.email]
            if part
        ]
        print(f"  - Contact:       {', '.join(contact_parts)}")
    print(f"  - CTA:           \"{prop.cta}\"")
    return 0


def cmd_make(args: argparse.Namespace) -> int:
    """Generate property promotional video and accompanying artifacts."""
    import time
    start_time = time.time()

    prop, base_dir = load_property(args.input)
    valid_images = check_images(prop.images, base_dir)

    # For M3, use deterministic template script
    from propvid.scriptgen.template import build_template_script
    script = build_template_script(prop)

    resolution = (1920, 1080) if args.res == "1080p" else (1280, 720)
    fps = 24

    from propvid.planner import plan_timeline
    plan, warnings = plan_timeline(
        prop, script, valid_images, resolution=resolution, fps=fps
    )

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    video_path = out_dir / "video.mp4"
    script_path = out_dir / "script.json"
    srt_path = out_dir / "captions.srt"
    share_path = out_dir / "share_copy.txt"
    report_path = out_dir / "run_report.json"

    # Save script JSON
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script.model_dump_json(indent=2))

    # Save SubRip captions
    from propvid.outputs import write_report, write_share_copy, write_srt
    write_srt(plan, srt_path)

    # Save share copy
    write_share_copy(prop, script, share_path)

    # Encode video (silent MP4 for M3 or audio when integrated)
    from propvid.render.encode import encode_video
    encode_video(plan, video_path)

    elapsed_time = time.time() - start_time
    timings = {"total_elapsed_seconds": round(elapsed_time, 2)}

    # Save run report
    write_report(
        input_facts=prop,
        output_path=report_path,
        total_duration=plan.total_duration,
        llm_used=False,
        warnings=warnings,
        timings=timings,
    )

    # Final summary message
    size_mb = video_path.stat().st_size / (1024 * 1024)
    print("\n[OK] Video generation complete!")
    print(f"  - Video path:    {video_path}")
    print(f"  - Duration:      {plan.total_duration:.1f} s ({len(plan.scenes)} scenes)")
    print(f"  - Resolution:    {resolution[0]}x{resolution[1]} @ {fps} fps")
    print(f"  - File size:     {size_mb:.2f} MB")
    print(f"  - Artifacts:     {script_path.name}, {srt_path.name}, {share_path.name}, {report_path.name}")
    print(f"  - Render time:   {elapsed_time:.1f} s")
    print(f"\nTo view the video, run:")
    print(f"  xdg-open {video_path}   # (Linux) or open in your media player")

    if args.open:
        import subprocess
        try:
            opener = "xdg-open" if sys.platform.startswith("linux") else ("open" if sys.platform == "darwin" else "start")
            subprocess.run([opener, str(video_path)], check=False)
        except Exception:
            pass

    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Interactively generate a property.json template."""
    print("not implemented yet (milestone 6)")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """System health and environment check."""
    print("not implemented yet (milestone 6)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="propvid",
        description="Propvid: Deterministic & AI-Polished Property Video Generator",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print full stack traces on error and enable debug logging",
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # validate command
    val_parser = subparsers.add_parser("validate", help="Validate a property input JSON and images")
    val_parser.add_argument(
        "-i", "--input",
        required=True,
        type=Path,
        help="Path to property.json input file",
    )

    # make command
    make_parser = subparsers.add_parser("make", help="Generate video from property specification")
    make_parser.add_argument(
        "-i", "--input",
        required=True,
        type=Path,
        help="Path to property.json input file",
    )
    make_parser.add_argument(
        "-o", "--out",
        required=True,
        type=Path,
        help="Output directory path",
    )
    make_parser.add_argument(
        "--llm",
        choices=["auto", "off"],
        default="auto",
        help="LLM script polish mode (default: auto)",
    )
    make_parser.add_argument(
        "--tts",
        choices=["auto", "kokoro", "fish", "none"],
        default="auto",
        help="TTS voice-over backend (default: auto)",
    )
    make_parser.add_argument(
        "--res",
        choices=["720p", "1080p"],
        default="720p",
        help="Video resolution (default: 720p)",
    )
    make_parser.add_argument(
        "--music",
        default="synth",
        help="Background music: 'synth' (default), 'none', or path to audio file",
    )
    make_parser.add_argument(
        "--open",
        action="store_true",
        help="Automatically open generated video when completed",
    )

    # init command
    init_parser = subparsers.add_parser("init", help="Interactively generate a property JSON")
    init_parser.add_argument(
        "-o", "--out",
        type=Path,
        default=Path("property.json"),
        help="Destination JSON file path",
    )

    # doctor command
    doc_parser = subparsers.add_parser("doctor", help="Check local environment, FFmpeg, fonts, and API connectivity")
    doc_parser.add_argument(
        "--ping",
        action="store_true",
        help="Send a test ping to OpenRouter API (costs a tiny fraction of a cent)",
    )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main CLI entrypoint with graceful error handling and exit codes."""
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(debug=args.debug)

    try:
        if args.subcommand == "validate":
            return cmd_validate(args)
        elif args.subcommand == "make":
            return cmd_make(args)
        elif args.subcommand == "init":
            return cmd_init(args)
        elif args.subcommand == "doctor":
            return cmd_doctor(args)
        else:
            parser.print_help(sys.stderr)
            return 2
    except InputError as exc:
        if args.debug:
            traceback.print_exc()
        print(f"Error: {exc.message}", file=sys.stderr)
        return exc.exit_code
    except RenderError as exc:
        if args.debug:
            traceback.print_exc()
        print(f"Error: {exc.message}", file=sys.stderr)
        return exc.exit_code
    except PropvidError as exc:
        if args.debug:
            traceback.print_exc()
        print(f"Error: {exc.message}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        if args.debug:
            traceback.print_exc()
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
