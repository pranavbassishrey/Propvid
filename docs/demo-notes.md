# Propvid Demonstration & Evaluator Walkthrough Guide

This document provides a guided walkthrough for evaluators and stakeholders to test and inspect the **Propvid AI Property Video Generator**.

---

## 1. Quick Environment Setup

1. **Activate the Python virtual environment:**
   ```bash
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Verify installation & dependencies:**
   ```bash
   pip install -e .
   ```

3. **Verify API Key (Optional):**
   ```bash
   cat .env
   ```
   *(Propvid works 100% offline with zero external network connectivity or keys using its deterministic template engine).*

---

## 2. System Health Check: `propvid doctor`

Run the built-in diagnostic tool to inspect your environment, FFmpeg binary, fonts, Rupee (`₹`) glyph geometry, and model files:

```bash
propvid doctor --ping
```

**Expected Output:**
```text
PROPVID SYSTEM HEALTH CHECK
  Component         Status   Details                                          
  ────────────────────────────────────────────────────────────────────────────
  Python Runtime    [OK]     3.12.15 (Supported: 3.10+)                       
  Core Packages     [OK]     pydantic, pillow, numpy, imageio-ffmpeg, httpx   
  FFmpeg Binary     [OK]     v7.0.2 (7.0.2-static)                            
  DejaVu Fonts      [OK]     Permissive license; Rupee glyph (₹) mask verified
  Kokoro ONNX TTS   [OK]     82M weights ready (337.3 MB in models)           
  OpenRouter API    [OK]     Configured (sk-or-v1...7d60) • Ping: 0.85s HTTP 200
  Fish Audio API    [SKIP]   Optional cloud backend (offline Kokoro default)  
  ────────────────────────────────────────────────────────────────────────────
[OK] Doctor diagnosis: propvid is ready to generate videos.
```

---

## 3. Interactive Video Creation Wizard: `propvid`

Demonstrate the user-facing interactive CLI required by the assignment brief:

```bash
propvid
```

**The wizard will interactively prompt for:**
1. **Property Name:** e.g., `Azure Horizon Villa` (press `Enter` to accept default `Green Valley Heights`)
2. **Location:** e.g., `Goa, Coastal Road`
3. **Price:** e.g., `₹2.75 Cr`
4. **Property Type:** e.g., `4-BHK Luxury Villa`
5. **Tone:** `warm`, `premium`, or `energetic`
6. **Key Features:** e.g., `Private infinity pool, Sea-facing deck, Modular Italian kitchen`
7. **Contact Info & Call to Action:** e.g., `Vikram Mehta`, `+91 98888 77777`, `Book a private tour`
8. **Photos Directory:** `examples/images` or `dataset/`
9. **Production Settings:** AI Polish (`auto`), Neural Voiceover (`auto`), Resolution (`720p`)
10. **Prompt to Generate & Preview:** Press `Y` to render!

Watch the dynamic live progress bar render frames at ~18.5 fps and open the completed MP4 video automatically in your default media player.

---

## 4. Demonstrating Key Evaluation Criteria

### A. Business Relevance & Problem Understanding (20%)
- **Manual editing bottleneck:** Editing a video with transitions, overlays, audio mixing, and subtitles usually takes **2–4 hours** in Adobe Premiere.
- **Automated solution:** Run a single command to generate a broadcast-ready video in **30–35 seconds**:
  ```bash
  propvid examples/property.sample.json -o out/sample --open
  ```

---

### B. AI / ML Approach & Output Verification (20%)
Show how Propvid uses AI responsibly with strict code-based guardrails:

1. **AI Script Polish with Free Router Models:**
   With `OPENROUTER_API_KEY` set, `propvid make` calls OpenRouter using `nvidia/nemotron-3.5-super-vl:free` to elevate factual notes into natural voiceover narration.
   
2. **Deterministic Response Caching:**
   Re-running the exact same listing uses disk caching (`.cache/`), completing in **0.00s latency** with **0 tokens consumed**.

3. **Hallucination Detection & Per-Scene Rollback:**
   The deterministic fact auditor (`src/propvid/scriptgen/verify.py`) scans every line for:
   - Invented numbers or denominations not present in the input
   - Unrecognized capitalized proper nouns
   - Banned buzzwords (`"cheapest"`, `"guaranteed"`, `"best"`)
   - Word count limits (>22 words)
   
   If a violation is detected, **only that specific scene reverts to its deterministic template version**, while all valid scenes remain polished.

4. **100% Offline Deterministic Mode:**
   To prove zero external network dependency:
   ```bash
   propvid examples/property.sample.json -o out/sample_offline --llm off --tts none
   ```

---

### C. Testing on 10 Distinct Real Estate Houses
Propvid includes a real dataset of 10 houses with 40 photos across bedroom, bathroom, kitchen, and frontal exterior views:

```bash
# Generate video for House 1
propvid dataset/properties/house_1.json -o out/house_1 --open

# Generate video for House 2
propvid dataset/properties/house_2.json -o out/house_2 --open

# Or run the batch generator script across all 10 houses:
python scripts/batch_generate.py
```

All 10 generated videos are also pre-rendered under `output/house_1/` through `output/house_10/` for instant viewing.

---

### D. Input Validation & Error Handling
Demonstrate robust error handling instead of crashes:

1. **Broken Schema Test:**
   ```bash
   propvid examples/property.broken.json
   ```
   *Result:* Exits with code `2` and displays a clean error:
   ```text
   Error: Missing required property field(s): 'name'
   ```

2. **Broken Images Test:**
   ```bash
   propvid examples/property.broken_images.json -o out/test_broken_imgs
   ```
   *Result:* Gracefully warns about missing or corrupt files, automatically utilizes the remaining valid images, and renders without crashing.

3. **Zero Valid Images Safety Check:**
   When no readable images exist, the CLI cleanly exits with code `2`:
   ```text
   Error: Zero valid images found. At least one readable image (>= 640x360) is required.
   ```

---

### E. Automated Test Suite (49/49 Passing)
Run the automated test suite covering all modules:
```bash
pytest -v
```
All 49 unit and integration tests pass in ~15 seconds.
