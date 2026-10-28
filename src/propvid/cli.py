"""Command-line interface for propvid."""

import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
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
    input_path = getattr(args, "input", None) or getattr(args, "input_pos", None)
    if not input_path:
        raise InputError("Input property file is required (pass -i PATH or positional PATH)")
    prop, base_dir = load_property(input_path)
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

    input_path = getattr(args, "input", None) or getattr(args, "input_pos", None)
    if not input_path:
        raise InputError("Input property file is required (pass -i PATH or positional PATH)")
    
    out_dir = args.out
    if not out_dir:
        stem = input_path.stem.replace("property.", "")
        out_dir = Path("out") / (stem if stem else "output")

    prop, base_dir = load_property(input_path)
    valid_images = check_images(prop.images, base_dir)

    # 1. Script generation (deterministic template with optional LLM polish)
    from propvid.config import get_settings
    from propvid.scriptgen import generate_script
    settings = get_settings()
    script, llm_report = generate_script(prop, llm_mode=args.llm, settings=settings)
    if llm_report.llm_used:
        print(f"  - LLM polish:    Active (model: {llm_report.model_used}, cache_hit: {llm_report.cache_hit})")
        if llm_report.reverted_scenes:
            print(f"  - Fact audit:    Reverted {len(llm_report.reverted_scenes)} scene(s) to template: {', '.join(llm_report.reverted_scenes)}")
    else:
        if args.llm != "off" and llm_report.error:
            logger.info("LLM polish skipped: %s", llm_report.error)

    # 2. TTS Voice-over synthesis (strictly preceding timeline planning)
    from propvid.audio.tts_base import get_backend, normalize_for_speech
    tts_backend = get_backend(args.tts)

    narration_clips = {}
    narration_durations = {}

    for scene in script.scenes:
        if args.tts != "none" and scene.narration.strip():
            spoken_text = normalize_for_speech(scene.narration)
            try:
                clip_arr, clip_sr = tts_backend.synth(spoken_text, scene.direction)
                if len(clip_arr) > 0 and clip_sr > 0:
                    narration_clips[scene.id] = (clip_arr, clip_sr)
                    narration_durations[scene.id] = len(clip_arr) / float(clip_sr)
            except Exception as exc:
                logger.warning("TTS generation skipped for scene %s: %s", scene.id, exc)

    resolution = (1920, 1080) if args.res == "1080p" else (1280, 720)
    fps = 24

    # 3. Timeline planning incorporating actual speech durations
    from propvid.planner import plan_timeline
    plan, warnings = plan_timeline(
        prop,
        script,
        valid_images,
        resolution=resolution,
        fps=fps,
        narration_durations=narration_durations,
    )

    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    video_path = out_dir / "video.mp4"
    script_path = out_dir / "script.json"
    srt_path = out_dir / "captions.srt"
    share_path = out_dir / "share_copy.txt"
    report_path = out_dir / "run_report.json"
    wav_path = out_dir / "mix.wav"

    # 4. Background music synthesis or loading
    music_arr = None
    if args.music == "synth":
        from propvid.audio.music import synth_ambient
        music_arr = synth_ambient(plan.total_duration)
    elif args.music != "none":
        from propvid.audio.music import load_audio_file
        try:
            music_arr = load_audio_file(Path(args.music))
        except Exception as exc:
            logger.warning("Could not load music file '%s': %s. Falling back to ambient synth.", args.music, exc)
            from propvid.audio.music import synth_ambient
            music_arr = synth_ambient(plan.total_duration)

    # 5. Audio track mixing
    has_audio = (len(narration_clips) > 0) or (music_arr is not None and len(music_arr) > 0)
    final_audio_path = None
    if has_audio:
        from propvid.audio.mix import mix_audio_track
        mix_audio_track(plan, narration_clips, music_arr, wav_path)
        final_audio_path = wav_path

    # 6. Save script JSON, SRT, and share copy
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script.model_dump_json(indent=2))

    from propvid.outputs import write_report, write_share_copy, write_srt
    write_srt(plan, srt_path)
    write_share_copy(prop, script, share_path)

    # 7. Render frames and encode video with muxed audio
    from propvid.render.encode import encode_video
    encode_video(plan, video_path, audio_path=final_audio_path)

    elapsed_time = time.time() - start_time
    timings = {
        "total_elapsed_seconds": round(elapsed_time, 2),
        "llm_latency_seconds": llm_report.latency_sec,
    }

    # 8. Save run report
    write_report(
        input_facts=prop,
        output_path=report_path,
        total_duration=plan.total_duration,
        llm_used=llm_report.llm_used,
        models_requested=llm_report.models_requested,
        model_used=llm_report.model_used,
        cache_hit=llm_report.cache_hit,
        tokens=llm_report.tokens,
        reverted_scenes=llm_report.reverted_scenes,
        warnings=warnings + ([llm_report.error] if llm_report.error else []),
        timings=timings,
    )

    # Final summary message
    size_mb = video_path.stat().st_size / (1024 * 1024)
    print("\n[OK] Video generation complete!")
    print(f"  - Video path:    {video_path}")
    print(f"  - Duration:      {plan.total_duration:.1f} s ({len(plan.scenes)} scenes)")
    print(f"  - Resolution:    {resolution[0]}x{resolution[1]} @ {fps} fps")
    print(f"  - File size:     {size_mb:.2f} MB")
    print(f"  - Audio:         {'Speech + Music' if (narration_clips and music_arr is not None) else ('Speech only' if narration_clips else ('Music only' if music_arr is not None else 'Silent'))}")
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
    out_path = Path(args.out)

    def _prompt(msg: str, default: str) -> str:
        if not sys.stdin.isatty() or getattr(args, "defaults", False):
            return default
        try:
            val = input(f"{msg} [{default}]: ").strip()
            return val if val else default
        except (EOFError, KeyboardInterrupt):
            print()
            return default

    print("Initialize Property Video Specification:")
    print("-" * 50)
    name = _prompt("Property name", "Green Valley Heights")
    location = _prompt("Location", "Whitefield, Bengaluru")
    price = _prompt("Price", "₹1.25 Cr")
    property_type = _prompt("Property type", "2 BHK Luxury Apartment")

    tone = _prompt("Tone (warm/premium/energetic)", "warm").lower()
    if tone not in ("warm", "premium", "energetic"):
        tone = "warm"

    features_raw = _prompt(
        "Features (comma-separated)",
        "Modular kitchen, East-facing balcony, Covered parking",
    )
    features = [f.strip() for f in features_raw.split(",") if f.strip()][:6]

    contact_name = _prompt("Contact person name (optional)", "Asha Rao")
    contact_phone = _prompt("Contact phone (optional)", "+91 90000 00000")
    contact_email = _prompt("Contact email (optional)", "sales@example.com")
    cta = _prompt("Call to Action", "Book your site visit today")

    images_dir_str = _prompt("Images directory or path", "examples/images")
    images_dir = Path(images_dir_str)
    images = []
    if images_dir.is_dir():
        for p in sorted(images_dir.glob("*.jpg")) + sorted(images_dir.glob("*.png")):
            try:
                rel_path = os.path.relpath(p, out_path.parent)
            except ValueError:
                rel_path = str(p)
            images.append({"path": rel_path})

    if not images:
        default_imgs = [
            ("examples/images/01_exterior.jpg", "Exterior", None),
            ("examples/images/02_living_room.jpg", "Living Room", None),
            ("examples/images/03_kitchen.jpg", "Kitchen", features[0] if features else "Modular kitchen"),
            ("examples/images/05_bedroom.jpg", "Bedroom", None),
        ]
        for src, lbl, feat in default_imgs:
            try:
                rel_path = os.path.relpath(src, out_path.parent)
            except ValueError:
                rel_path = src
            img_entry = {"path": rel_path, "label": lbl}
            if feat:
                img_entry["feature"] = feat
            images.append(img_entry)

    data = {
        "name": name,
        "location": location,
        "price": price,
        "property_type": property_type,
        "tone": tone,
        "features": features,
        "images": images,
        "contact": {
            "name": contact_name,
            "phone": contact_phone,
            "email": contact_email,
        },
        "cta": cta,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[OK] Property specification written to {out_path}")
    print(f"You can now run: propvid make -i {out_path} -o out/demo")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """System health, environment check, and diagnostic report."""
    from propvid.config import get_settings
    settings = get_settings()

    print("propvid system diagnostic doctor:")
    print("=" * 60)

    all_passed = True

    # 1. Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        print(f"  [OK] Python version: {py_ver}")
    else:
        print(f"  [FAIL] Python version: {py_ver} (Python 3.10+ required)")
        all_passed = False

    # 2. Core Python dependencies
    import importlib.metadata
    core_pkgs = ["pydantic", "pillow", "numpy", "imageio_ffmpeg", "httpx"]
    missing_pkgs = []
    for pkg in core_pkgs:
        try:
            _ = importlib.metadata.version(pkg.replace("_", "-"))
        except Exception:
            try:
                _ = importlib.metadata.version(pkg)
            except Exception:
                missing_pkgs.append(pkg)
    if not missing_pkgs:
        print("  [OK] Core dependencies installed: pydantic, pillow, numpy, imageio-ffmpeg, httpx")
    else:
        print(f"  [FAIL] Missing core dependencies: {', '.join(missing_pkgs)}")
        all_passed = False

    # 3. FFmpeg binary
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        res = subprocess.run([ffmpeg_exe, "-version"], capture_output=True, text=True, check=False)
        first_line = res.stdout.splitlines()[0] if res.stdout else "unknown"
        print(f"  [OK] FFmpeg available: {ffmpeg_exe} ({first_line})")
    except Exception as exc:
        print(f"  [FAIL] FFmpeg is not available: {exc}")
        all_passed = False

    # 4. Font and Rupee Glyph
    from propvid.render.text import font_has_glyph, load_font
    try:
        font_regular = load_font(24, bold=False)
        has_rupee = font_has_glyph(font_regular, "₹")
        if has_rupee:
            print("  [OK] Fonts available and Rupee glyph (₹) mask verified (Bitstream Vera/DejaVu)")
        else:
            print("  [WARN] Fonts found but Rupee glyph (₹) mask failed check")
    except Exception as exc:
        print(f"  [FAIL] Font check failed: {exc}")
        all_passed = False

    # 5. Kokoro TTS models
    k_model = settings.models_dir / "kokoro-v1.0.onnx"
    k_voices = settings.models_dir / "voices-v1.0.bin"
    if k_model.exists() and k_voices.exists():
        size_mb = (k_model.stat().st_size + k_voices.stat().st_size) / (1024 * 1024)
        print(f"  [OK] Kokoro TTS models present ({size_mb:.1f} MB in {settings.models_dir})")
    else:
        print(f"  [WARN] Kokoro TTS models missing in {settings.models_dir} (run 'python scripts/download_tts_models.py')")

    # 6. OpenRouter API Key
    if settings.openrouter_api_key:
        masked_key = settings.openrouter_api_key[:8] + "..." + settings.openrouter_api_key[-4:]
        models_str = ", ".join(settings.openrouter_models[:3])
        print(f"  [OK] OpenRouter API key found ({masked_key}, models: {models_str})")
        if getattr(args, "ping", False):
            print("       Pinging OpenRouter API...", end=" ", flush=True)
            try:
                import httpx, time
                t0 = time.time()
                resp = httpx.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openrouter_api_key}", "Content-Type": "application/json"},
                    json={
                        "model": settings.openrouter_models[0],
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5,
                        "reasoning": {"max_tokens": 0},
                    },
                    timeout=15.0,
                )
                dt = time.time() - t0
                if resp.status_code == 200:
                    model_resp = resp.json().get("model", settings.openrouter_models[0])
                    print(f"Success! (HTTP 200 in {dt:.2f}s, model: {model_resp})")
                else:
                    print(f"HTTP {resp.status_code} ({resp.text[:100]})")
            except Exception as exc:
                print(f"Ping failed: {exc}")
    else:
        print("  [-] OPENROUTER_API_KEY not set (optional; will use deterministic template script)")

    # 7. Fish Audio API Key
    if settings.fish_api_key:
        print("  [OK] FISH_API_KEY found")
    else:
        print("  [-] FISH_API_KEY not configured (optional cloud TTS backend)")

    print("=" * 60)
    if all_passed:
        print("[OK] Doctor diagnosis: propvid is ready to generate videos.")
        return 0
    else:
        print("[FAIL] Doctor diagnosis: some required components are missing.")
        return 1


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

    subparsers = parser.add_subparsers(dest="subcommand", required=False)

    # validate command
    val_parser = subparsers.add_parser("validate", help="Validate a property input JSON and images")
    val_parser.add_argument(
        "input_pos",
        nargs="?",
        type=Path,
        default=None,
        help="Path to property.json input file (positional)",
    )
    val_parser.add_argument(
        "-i", "--input",
        type=Path,
        default=None,
        help="Path to property.json input file",
    )

    # make command
    make_parser = subparsers.add_parser("make", help="Generate video from property specification")
    make_parser.add_argument(
        "input_pos",
        nargs="?",
        type=Path,
        default=None,
        help="Path to property.json input file (positional)",
    )
    make_parser.add_argument(
        "-i", "--input",
        type=Path,
        default=None,
        help="Path to property.json input file",
    )
    make_parser.add_argument(
        "-o", "--out",
        type=Path,
        default=None,
        help="Output directory path (default: out/<property_stem>)",
    )
    make_parser.add_argument(
        "--llm",
        choices=["auto", "off", "on"],
        default="auto",
        help="LLM script polish mode: 'auto' (default), 'off', or 'on'",
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
    init_parser.add_argument(
        "--defaults",
        action="store_true",
        help="Use default values non-interactively",
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
    if argv is None:
        argv = sys.argv[1:]
    else:
        argv = list(argv)

    # If first positional argument isn't a known subcommand or help flag, default to 'make'
    subcommands = {"validate", "make", "init", "doctor"}
    has_subcommand = any(arg in subcommands for arg in argv)
    is_help = any(arg in {"-h", "--help"} for arg in argv)
    if not has_subcommand and not is_help and len(argv) > 0:
        if argv[0] == "--debug":
            argv = ["--debug", "make"] + argv[1:]
        else:
            argv = ["make"] + argv

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
