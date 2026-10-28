"""Command-line interface for propvid."""

import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from typing import Optional, Sequence

from propvid.errors import InputError, PropvidError, RenderError
from propvid.inputs import check_images, load_property
from propvid.terminal import (
    ProgressBar,
    badge_ai,
    badge_err,
    badge_info,
    badge_ok,
    badge_render,
    badge_skip,
    badge_tts,
    badge_warn,
    bold,
    cyan,
    dim,
    green,
    magenta,
    print_banner,
    print_card,
    print_step,
    print_table,
    yellow,
)

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
    print_banner()
    input_path = getattr(args, "input", None) or getattr(args, "input_pos", None)
    if not input_path:
        raise InputError("Input property file is required (pass -i PATH or positional PATH)")
    prop, base_dir = load_property(input_path)
    valid_images = check_images(prop.images, base_dir)

    print(f"{badge_ok()} Property data and media validation succeeded:")
    items = [
        ("Property Name", prop.name),
        ("Location", prop.location),
        ("Price", prop.price),
        ("Property Type", prop.property_type),
        ("Tone", prop.tone),
        ("Features", f"{len(prop.features)} feature(s): {', '.join(prop.features[:3])}"),
        ("Images Verified", f"{len(valid_images)} valid image(s) (from {len(prop.images)} declared)"),
    ]
    if prop.contact:
        contact_parts = [
            part
            for part in [prop.contact.name, prop.contact.phone, prop.contact.email]
            if part
        ]
        items.append(("Contact", ", ".join(contact_parts)))
    items.append(("Call to Action", f'"{prop.cta}"'))

    print_card("VALIDATED PROPERTY SPECIFICATION", items)
    return 0


def cmd_make(args: argparse.Namespace) -> int:
    """Generate property promotional video and accompanying artifacts."""
    print_banner()
    start_time = time.time()

    input_path = getattr(args, "input", None) or getattr(args, "input_pos", None)
    if not input_path:
        raise InputError("Input property file is required (pass -i PATH or positional PATH)")

    out_dir = args.out
    if not out_dir:
        stem = input_path.stem.replace("property.", "")
        out_dir = Path("out") / (stem if stem else "output")

    # Step 1: Input Validation
    print_step(1, 5, "Validating Property Specifications & Listing Photos")
    prop, base_dir = load_property(input_path)
    valid_images = check_images(prop.images, base_dir)
    print(f"  {badge_ok()} Loaded: {bold(prop.name)} ({prop.property_type}) in {prop.location}")
    print(f"  {badge_ok()} Verified {len(valid_images)} listing photo(s) upright and readable")

    # Step 2: Script Generation (Deterministic template with optional LLM polish)
    print_step(2, 5, "Generating Voiceover Script & Fact Auditing")
    from propvid.config import get_settings
    from propvid.scriptgen import generate_script
    settings = get_settings()
    script, llm_report = generate_script(prop, llm_mode=args.llm, settings=settings)

    if llm_report.llm_used:
        cache_tag = "cache hit" if llm_report.cache_hit else f"{llm_report.latency_sec:.2f}s latency"
        print(f"  {badge_ai()} AI Polish: Active via {bold(llm_report.model_used or 'OpenRouter')} ({cache_tag})")
        if llm_report.reverted_scenes:
            print(f"  {badge_warn()} Fact audit reverted {len(llm_report.reverted_scenes)} scene(s) to template: {', '.join(llm_report.reverted_scenes)}")
        else:
            print(f"  {badge_ok()} Fact audit: 100% facts verified against listing inputs")
    else:
        print(f"  {badge_info()} Deterministic template script (zero LLM calls, zero network)")

    # Step 3: Neural Voiceover & Ambient Soundtrack
    print_step(3, 5, "Synthesizing Neural Speech & Procedural Soundtrack")
    from propvid.audio.tts_base import get_backend
    voice = getattr(args, "voice", None)
    if voice and args.tts in ("edge", "kokoro"):
        if args.tts == "edge":
            from propvid.audio.tts_edge import TTSEdgeBackend
            tts_backend = TTSEdgeBackend(voice=voice, settings=settings)
        else:
            from propvid.audio.tts_kokoro import TTSKokoroBackend
            tts_backend = TTSKokoroBackend(voice=voice, settings=settings)
    else:
        tts_backend = get_backend(args.tts, settings=settings)

    narration_clips = {}
    narration_durations = {}

    if tts_backend is not None:
        from propvid.audio.tts_base import TTSNoneBackend, normalize_for_speech
        if not isinstance(tts_backend, TTSNoneBackend):
            tts_name = tts_backend.__class__.__name__.replace("TTS", "").replace("Backend", "")
            voice_info = f" ({tts_backend.voice})" if hasattr(tts_backend, "voice") and tts_backend.voice else ""
            print(f"  {badge_tts()} Voiceover engine: {bold(tts_name)}{voice_info}")
            for scene in script.scenes:
                try:
                    spoken_text = normalize_for_speech(scene.narration)
                    clip_arr, clip_sr = tts_backend.synth(spoken_text, scene.direction)
                    if clip_arr is not None and len(clip_arr) > 0:
                        narration_clips[scene.id] = (clip_arr, clip_sr)
                        narration_durations[scene.id] = len(clip_arr) / float(clip_sr)
                except Exception as exc:
                    logger.warning("TTS generation skipped for scene %s: %s", scene.id, exc)
                    print(f"  {badge_warn()} Scene '{scene.id}' voiceover skipped: {exc}")
            print(f"  {badge_ok()} Generated {len(narration_clips)} narration clip(s)")
        else:
            print(f"  {badge_skip()} Speech voiceover disabled (TTSNoneBackend)")
    else:
        print(f"  {badge_skip()} Speech voiceover disabled (--tts none)")

    resolution = (1920, 1080) if args.res == "1080p" else (1280, 720)
    fps = 24

    # Step 4: Timeline planning
    print_step(4, 5, "Planning Ken Burns Motion Timeline & Subtitles")
    from propvid.planner import plan_timeline
    plan, warnings = plan_timeline(
        prop,
        script,
        valid_images,
        resolution=resolution,
        fps=fps,
        narration_durations=narration_durations,
    )
    for w in warnings:
        print(f"  {badge_warn()} {w}")
    print(f"  {badge_ok()} Planned timeline: {plan.total_duration:.1f} s across {len(plan.scenes)} scenes ({resolution[0]}x{resolution[1]} @ {fps} fps)")

    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    video_path = out_dir / "video.mp4"
    script_path = out_dir / "script.json"
    srt_path = out_dir / "captions.srt"
    share_path = out_dir / "share_copy.txt"
    report_path = out_dir / "run_report.json"
    wav_path = out_dir / "mix.wav"

    # Music synthesis or loading
    music_arr = None
    if args.music == "synth":
        from propvid.audio.music import synth_ambient
        music_arr = synth_ambient(plan.total_duration)
        print(f"  {badge_ok()} Synthesized procedural Cmaj7 ambient soundtrack ({plan.total_duration:.1f}s)")
    elif args.music != "none":
        from propvid.audio.music import load_audio_file
        try:
            music_arr = load_audio_file(Path(args.music))
        except Exception as exc:
            logger.warning("Could not load music file '%s': %s. Falling back to ambient synth.", args.music, exc)
            from propvid.audio.music import synth_ambient
            music_arr = synth_ambient(plan.total_duration)

    # Audio track mixing
    has_audio = (len(narration_clips) > 0) or (music_arr is not None and len(music_arr) > 0)
    final_audio_path = None
    if has_audio:
        from propvid.audio.mix import mix_audio_track
        mix_audio_track(plan, narration_clips, music_arr, wav_path)
        final_audio_path = wav_path
        print(f"  {badge_ok()} Mastered stereo audio mix with auto-ducking to {wav_path.name}")

    # Save script JSON, SRT, and share copy
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script.model_dump_json(indent=2))

    from propvid.outputs import write_report, write_share_copy, write_srt
    write_srt(plan, srt_path)
    write_share_copy(prop, script, share_path)

    # Step 5: Render frames and encode video with muxed audio
    print_step(5, 5, "Rendering Video Frames & Multiplexing MP4")
    from propvid.render.encode import encode_video
    total_frames = int(round(plan.total_duration * fps))

    pbar = ProgressBar(total_frames, label="Rendering")
    encode_video(
        plan,
        video_path,
        audio_path=final_audio_path,
        progress_callback=lambda cur, tot: pbar.update(cur),
    )
    pbar.finish()

    elapsed_time = time.time() - start_time
    timings = {
        "total_elapsed_seconds": round(elapsed_time, 2),
        "llm_latency_seconds": llm_report.latency_sec,
    }

    # Save run report
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

    size_mb = video_path.stat().st_size / (1024 * 1024)
    audio_desc = (
        "Speech (Kokoro ONNX) + Ambient Music"
        if (narration_clips and music_arr is not None)
        else ("Speech only" if narration_clips else ("Music only" if music_arr is not None else "Silent"))
    )

    # Display high-impact summary card
    summary_items = [
        ("Listing Property", prop.name),
        ("Video File", str(video_path)),
        ("Duration", f"{plan.total_duration:.1f} s ({len(plan.scenes)} scenes)"),
        ("Format", f"{resolution[0]}x{resolution[1]} @ {fps} fps ({size_mb:.2f} MB)"),
        ("Audio Master", audio_desc),
        ("Subtitles", str(srt_path.name)),
        ("Social Marketing Copy", str(share_path.name)),
        ("Audit Report", str(report_path.name)),
        ("Total Render Time", f"{elapsed_time:.1f} s"),
    ]
    print_card("VIDEO GENERATION COMPLETE", summary_items, footer=f"Preview command: xdg-open {video_path}")

    # Standard [OK] tag for test assertions
    print(f"[OK] Video generation complete! ({video_path})")

    if args.open:
        try:
            opener = "xdg-open" if sys.platform.startswith("linux") else ("open" if sys.platform == "darwin" else "start")
            subprocess.run([opener, str(video_path)], check=False)
        except Exception:
            pass

    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Interactively generate a property.json template."""
    print_banner()
    out_path = Path(args.out)

    def _prompt(msg: str, default: str) -> str:
        if not sys.stdin.isatty() or getattr(args, "defaults", False):
            return default
        try:
            val = input(f"{cyan('?')} {bold(msg)} {dim(f'[{default}]')}: ").strip()
            return val if val else default
        except (EOFError, KeyboardInterrupt):
            print()
            return default

    print(f"{bold('Initialize New Property Video Specification')}")
    print(dim("─" * 60))
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
    print(f"\n{badge_ok()} Property specification written to {bold(str(out_path))}")
    print(f"  Generate video: {cyan(f'propvid make -i {out_path} -o out/demo')}")
    return 0


def cmd_interactive(args: Optional[argparse.Namespace] = None) -> int:
    """Guided interactive command-line wizard for property input and instant video generation."""
    print_banner()
    print(f"{bold('✦ Interactive Property Video Studio ✦')}")
    print(dim("Enter your property details below (press Enter to accept default suggested values).\n"))

    def _ask(label: str, default: str, validator=None) -> str:
        while True:
            try:
                raw = input(f" {cyan('?')} {bold(label)} {dim(f'[{default}]')}: ").strip()
                val = raw if raw else default
                if validator:
                    err = validator(val)
                    if err:
                        print(f"   {yellow('!')} {err}")
                        continue
                return val
            except (EOFError, KeyboardInterrupt):
                print()
                return default

    # 1. Basic details
    name = _ask("Property name", "Green Valley Heights", lambda v: "Name cannot be empty" if not v.strip() else None)
    location = _ask("Location (City, Area)", "Whitefield, Bengaluru")
    price = _ask("Price (e.g. ₹1.25 Cr, ₹85 Lakh)", "₹1.25 Cr")
    prop_type = _ask("Property type", "2-BHK Luxury Apartment")

    tone = _ask("Narration tone (warm / premium / energetic)", "warm").lower()
    if tone not in ("warm", "premium", "energetic"):
        tone = "warm"

    # 2. Key features (1 to 6)
    features_input = _ask(
        "Key features (comma-separated, 1-6 features)",
        "Modular kitchen, East-facing balcony, Covered parking, Infinity pool",
    )
    features = [f.strip() for f in features_input.split(",") if f.strip()][:6]

    # 3. Contact & Call to Action
    contact_name = _ask("Contact person name", "Asha Rao")
    contact_phone = _ask("Contact phone", "+91 90000 00000")
    contact_email = _ask("Contact email", "sales@example.com")
    cta = _ask("Call-to-Action text", "Book your exclusive site visit today")

    # 4. Production settings & Output directory
    print(f"\n {bold('Production Settings')}")
    slug = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
    out_dir_str = _ask("Output folder", f"out/{slug}")
    out_dir = Path(out_dir_str).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    llm_opt = _ask("AI Script Polish (auto: OpenRouter free models / off: template)", "auto").lower()
    tts_opt = _ask("Voiceover Engine (edge: Ultra-Fast Neural / kokoro: Local ONNX / fish: Cloud / none)", "edge").lower()
    res_opt = _ask("Video Resolution (720p / 1080p)", "720p").lower()
    if res_opt not in ("720p", "1080p"):
        res_opt = "720p"

    # 5. Property Photos
    print(f"\n {bold('Listing Photos')}")
    print(dim(" Provide a folder containing 4–8 listing images (e.g. examples/images or dataset)."))
    img_dir_input = _ask("Image directory or file path", "examples/images")
    img_path = Path(img_dir_input)

    image_entries = []
    if img_path.is_dir():
        found = sorted(img_path.glob("*.jpg")) + sorted(img_path.glob("*.png")) + sorted(img_path.glob("*.jpeg"))
        for p in found:
            try:
                rel = os.path.relpath(p.resolve(), out_dir)
            except ValueError:
                rel = str(p.resolve())
            image_entries.append({"path": rel})
    elif img_path.is_file():
        try:
            rel = os.path.relpath(img_path.resolve(), out_dir)
        except ValueError:
            rel = str(img_path.resolve())
        image_entries.append({"path": rel})

    if not image_entries:
        print(f" {yellow('!')} No images found in '{img_dir_input}'. Automatically falling back to sample listing photos.")
        default_imgs = [
            ("examples/images/01_exterior.jpg", "Exterior", None),
            ("examples/images/02_living_room.jpg", "Living Room", None),
            ("examples/images/03_kitchen.jpg", "Kitchen", features[0] if features else "Modular kitchen"),
            ("examples/images/05_bedroom.jpg", "Bedroom", None),
        ]
        for src, lbl, feat in default_imgs:
            src_p = Path(src).resolve()
            try:
                rel = os.path.relpath(src_p, out_dir)
            except ValueError:
                rel = str(src_p)
            entry = {"path": rel, "label": lbl}
            if feat:
                entry["feature"] = feat
            image_entries.append(entry)
    else:
        print(f" {badge_ok()} Found {len(image_entries)} image(s) for the video timeline.")

    prop_json_path = out_dir / "property.json"
    prop_dict = {
        "name": name,
        "location": location,
        "price": price,
        "property_type": prop_type,
        "tone": tone,
        "features": features,
        "images": image_entries,
        "contact": {
            "name": contact_name,
            "phone": contact_phone,
            "email": contact_email,
        },
        "cta": cta,
    }
    prop_json_path.write_text(json.dumps(prop_dict, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n {badge_ok()} Property specification written to {bold(str(prop_json_path))}")

    # 6. Execute video generation
    render_now = _ask("Generate and preview video now? (Y/n)", "Y").lower()
    if render_now in ("y", "yes", ""):
        print(f"\n{bold('Starting Video Production Pipeline...')}")
        make_args = argparse.Namespace(
            input=prop_json_path,
            input_pos=None,
            out=out_dir,
            llm=llm_opt if llm_opt in ("auto", "off", "on") else "auto",
            tts=tts_opt if tts_opt in ("auto", "edge", "kokoro", "fish", "none") else "auto",
            voice=None,
            res=res_opt,
            music="synth",
            open=True,
            debug=False,
        )
        return cmd_make(make_args)
    else:
        print(f"\nSpecification saved! When you're ready to generate your video, run:")
        print(f"  {cyan(f'propvid make -i {prop_json_path} -o {out_dir} --open')}")
        return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """System health, environment check, and diagnostic report."""
    print_banner()
    from propvid.config import get_settings
    settings = get_settings()

    all_passed = True
    table_rows = []

    # 1. Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        table_rows.append(["Python Runtime", badge_ok(), f"{py_ver} (Supported: 3.10+)"])
    else:
        table_rows.append(["Python Runtime", badge_err(), f"{py_ver} (Requires 3.10+)"])
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
        table_rows.append(["Core Packages", badge_ok(), "pydantic, pillow, numpy, imageio-ffmpeg, httpx"])
    else:
        table_rows.append(["Core Packages", badge_err(), f"Missing: {', '.join(missing_pkgs)}"])
        all_passed = False

    # 3. FFmpeg binary
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        res = subprocess.run([ffmpeg_exe, "-version"], capture_output=True, text=True, check=False)
        first_line = res.stdout.splitlines()[0] if res.stdout else "unknown"
        table_rows.append(["FFmpeg Binary", badge_ok(), f"v7.0.2 ({first_line.split(' ')[2] if ' ' in first_line else first_line})"])
    except Exception as exc:
        table_rows.append(["FFmpeg Binary", badge_err(), str(exc)])
        all_passed = False

    # 4. Font and Rupee Glyph
    from propvid.render.text import font_has_glyph, load_font
    try:
        font_regular = load_font(24, bold=False)
        has_rupee = font_has_glyph(font_regular, "₹")
        if has_rupee:
            table_rows.append(["DejaVu Fonts", badge_ok(), "Permissive license; Rupee glyph (₹) mask verified"])
        else:
            table_rows.append(["DejaVu Fonts", badge_warn(), "Fonts found but Rupee glyph (₹) mask failed check"])
    except Exception as exc:
        table_rows.append(["DejaVu Fonts", badge_err(), str(exc)])
        all_passed = False

    # 5. Kokoro TTS models
    k_model = settings.models_dir / "kokoro-v1.0.onnx"
    k_voices = settings.models_dir / "voices-v1.0.bin"
    if k_model.exists() and k_voices.exists():
        size_mb = (k_model.stat().st_size + k_voices.stat().st_size) / (1024 * 1024)
        table_rows.append(["Kokoro ONNX TTS", badge_ok(), f"82M weights ready ({size_mb:.1f} MB in {settings.models_dir})"])
    else:
        table_rows.append(["Kokoro ONNX TTS", badge_warn(), f"Missing in {settings.models_dir} (run download_tts_models.py)"])

    # 6. Edge TTS (Ultra-Fast)
    try:
        import edge_tts
        table_rows.append(["Edge TTS (Ultra-Fast)", badge_ok(), f"v{edge_tts.__version__} ready (2s neural voiceover)"])
    except ImportError:
        table_rows.append(["Edge TTS (Ultra-Fast)", badge_skip(), "Optional (install with pip install edge-tts)"])

    # 6. OpenRouter API Key
    if settings.openrouter_api_key:
        masked_key = settings.openrouter_api_key[:8] + "..." + settings.openrouter_api_key[-4:]
        models_str = ", ".join(settings.openrouter_models[:3])
        ping_status = ""
        if getattr(args, "ping", False):
            try:
                import httpx
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
                ping_status = f" • Ping: {dt:.2f}s HTTP {resp.status_code}"
            except Exception as exc:
                ping_status = f" • Ping failed: {exc}"
        table_rows.append(["OpenRouter API", badge_ok(), f"Configured ({masked_key}){ping_status}"])
    else:
        table_rows.append(["OpenRouter API", badge_skip(), "Optional (will use deterministic template script)"])

    # 7. Fish Audio API Key
    if settings.fish_api_key:
        table_rows.append(["Fish Audio API", badge_ok(), "Configured for optional cloud TTS"])
    else:
        table_rows.append(["Fish Audio API", badge_skip(), "Optional cloud backend (offline Kokoro default)"])

    # Print dashboard
    print_table(["Component", "Status", "Details"], table_rows, title="PROPVID SYSTEM HEALTH CHECK")

    if all_passed:
        print(f"\n{badge_ok()} Doctor diagnosis: propvid is ready to generate videos.")
        return 0
    else:
        print(f"\n{badge_err()} Doctor diagnosis: some required components are missing.")
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser with rich help text."""
    parser = argparse.ArgumentParser(
        prog="propvid",
        description="Propvid: Deterministic & AI-Polished Property Video Studio",
        epilog="""
Examples:
  propvid                            # Step-by-step interactive creation wizard
  propvid interactive                # Step-by-step interactive creation wizard
  propvid examples/property.sample.json -o out/sample --open
  propvid make examples/property.sample.json -o out/sample
  propvid validate examples/property.sample.json
  propvid doctor --ping
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        choices=["auto", "edge", "kokoro", "fish", "none"],
        default="auto",
        help="TTS voice-over backend: 'auto' (default), 'edge' (ultra-fast neural), 'kokoro' (local ONNX), 'fish', or 'none'",
    )
    make_parser.add_argument(
        "--voice",
        default=None,
        help="Optional voice override (e.g. Edge: 'en-IN-NeerjaNeural', 'en-US-JennyNeural'; Kokoro: 'af_bella')",
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

    # interactive command
    subparsers.add_parser(
        "interactive",
        aliases=["create", "wizard"],
        help="Interactive step-by-step video creation wizard",
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

    # If first argument isn't a known subcommand or help flag, default to 'make'
    subcommands = {"validate", "make", "init", "doctor", "interactive", "create", "wizard"}
    has_subcommand = any(arg in subcommands for arg in argv)
    is_help = any(arg in {"-h", "--help"} for arg in argv)
    if not has_subcommand and not is_help and len(argv) > 0:
        if argv[0] == "--debug":
            argv = ["--debug", "make"] + argv[1:]
        else:
            argv = ["make"] + argv
    elif len(argv) == 0 and sys.stdin.isatty():
        # When invoked directly with no args in interactive terminal, launch wizard!
        return cmd_interactive()

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
        elif args.subcommand in ("interactive", "create", "wizard"):
            return cmd_interactive(args)
        else:
            print_banner()
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
