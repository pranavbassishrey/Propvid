# Propvid Demonstration & Walkthrough Guide

This guide walks through setting up, inspecting, and demonstrating the complete `propvid` system locally.

---

## 1. Quick Environment Setup

1. **Create and activate Python virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-tts.txt
   pip install -e .
   ```

3. **Configure API Keys (Optional):**
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   Add your OpenRouter key:
   ```env
   OPENROUTER_API_KEY=sk-or-v1-...
   OPENROUTER_MODELS=nvidia/nemotron-3.5-super-vl:free,google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free
   ```
   *(Note: Propvid functions 100% offline with zero keys or network using its deterministic template mode).*

---

## 2. System Health Check: `propvid doctor`

Run the built-in diagnostic tool to verify all system components:

```bash
python -m propvid doctor
```

Example Output:
```text
propvid system diagnostic doctor:
============================================================
  [OK] Python version: 3.12.15
  [OK] Core dependencies installed: pydantic, pillow, numpy, imageio-ffmpeg, httpx
  [OK] FFmpeg available: ... (ffmpeg version 7.0.2-static)
  [OK] Fonts available and Rupee glyph (₹) mask verified (Bitstream Vera/DejaVu)
  [OK] Kokoro TTS models present (337.3 MB in models)
  [OK] OpenRouter API key found (sk-or-v1...7d60, models: nvidia/nemotron-3.5-super-vl:free, ...)
  [-] FISH_API_KEY not configured (optional cloud TTS backend)
============================================================
[OK] Doctor diagnosis: propvid is ready to generate videos.
```

To verify live network connectivity with a fast 5-token ping to OpenRouter:
```bash
python -m propvid doctor --ping
```

---

## 3. Interactive Specification Generator: `propvid init`

Create a new listing specification interactively:
```bash
python -m propvid init -o my_property.json
```
Prompts will guide you through property name, price, bedrooms, features, contact info, and images.

To generate a sample specification non-interactively:
```bash
python -m propvid init -o my_property.json --defaults
```

---

## 4. Input & Media Validation: `propvid validate`

Validate the specification and referenced image resolutions:
```bash
python -m propvid validate -i examples/property.sample.json
```

Output checks:
- Required schema fields (`name`, `location`, `price`, `property_type`)
- Image accessibility and orientation (`exif_transpose`)
- Minimum dimensions check ($\ge 640\times 360$ landscape or $\ge 300\times 450$ portrait)
- Verified contact & CTA configuration

---

## 5. Generating Promotional Videos: `propvid make`

### Standard Run (AI Polish + Neural Voiceover + Procedural Music):
```bash
python -m propvid make -i examples/property.sample.json -o out/sample --open
```

### Deterministic Offline Run (Zero LLM, Zero Network):
```bash
python -m propvid make -i examples/property.sample.json -o out/sample_offline --llm off --tts none
```

### Generated Artifacts in `out/sample/`:
- **`video.mp4`**: 1280x720 24 fps H.264 video with AAC audio (20–40s duration).
- **`mix.wav`**: 44.1kHz 16-bit PCM master audio track (speech + auto-ducked music).
- **`script.json`**: Scene timeline specification with headlines, captions, and narration.
- **`captions.srt`**: Standard SubRip subtitles synchronized to scene durations.
- **`share_copy.txt`**: Social media caption with listing highlights and hashtags.
- **`run_report.json`**: Execution report with model used, tokens, latency, and fact verification status.

---

## 6. Demonstrating Key Features to Stakeholders

### A. AI Script Polish with Automatic Fallback
Run `propvid make` with `--llm auto`. If an API key is present, it uses `nvidia/nemotron-3.5-super-vl:free` to polish headlines and narrations for conversational voiceover flow.
Re-running the exact same input uses the disk cache in `.cache/`, finishing in `0.0s` LLM latency with 0 API tokens consumed.

### B. Hallucination Guardrails & Per-Scene Reversion
If an LLM hallucinates an unverified number, proper noun, or banned buzzword (like `"guaranteed"` or `"cheapest"`), `propvid`'s code auditor flags the violation and **automatically reverts only that scene back to its deterministic factual template**, preserving all valid polished scenes.

### C. Testing on 10 Distinct Real Estate Properties
Run the batch generator across 10 real houses from the dataset:
```bash
python scripts/batch_generate.py
```
Videos will be generated under `output/house_1` through `output/house_10`.
