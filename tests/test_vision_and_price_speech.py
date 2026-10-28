"""Tests for two-step image recognition and price voiceover normalization."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from propvid.audio.tts_base import normalize_for_speech
from propvid.inputs import ValidImage
from propvid.schema import SceneSpec
from propvid.vision import (
    CATEGORY_BATHROOM,
    CATEGORY_BEDROOM,
    CATEGORY_DINING,
    CATEGORY_EXTERIOR,
    CATEGORY_KITCHEN,
    CATEGORY_LIVING,
    CATEGORY_PARKING,
    CATEGORY_POOL,
    classify_by_filename,
    classify_image,
    match_scenes_to_images,
)


def test_price_speech_normalization():
    """Verify exact price voiceover rules specified by candidate assignment."""
    # Decimal point with non-spaced digits and 'point'
    assert normalize_for_speech("1.75cr") == "one point 75 crores"
    assert normalize_for_speech("Priced at ₹1.75 Cr") == "Priced at one point 75 crores"
    assert normalize_for_speech("1.75crores") == "one point 75 crores"
    assert normalize_for_speech("0.95cr") == "zero point 95 crores"
    assert normalize_for_speech("12.5 Cr") == "twelve point 5 crores"

    # Lakhs for L
    assert normalize_for_speech("75l") == "75 lakhs"
    assert normalize_for_speech("₹75 L") == "75 lakhs"
    assert normalize_for_speech("1.5L") == "one point 5 lakhs"

    # Millions for M
    assert normalize_for_speech("2.5m") == "two point 5 millions"
    assert normalize_for_speech("$2.5M") == "two point 5 millions"

    # Billions for B
    assert normalize_for_speech("1.2b") == "one point 2 billions"

    # Thousands for K
    assert normalize_for_speech("500k") == "500 thousands"
    assert normalize_for_speech("50k") == "50 thousands"

    # Whole integers
    assert normalize_for_speech("56 Cr") == "56 crores"
    assert normalize_for_speech("96 Lakhs") == "96 lakhs"


def test_step1_filename_classification():
    """Step 1: Test keyword classification from filename stems."""
    assert classify_by_filename("12_kitchen.jpg") == CATEGORY_KITCHEN
    assert classify_by_filename("12_bathroom.jpg") == CATEGORY_BATHROOM
    assert classify_by_filename("washroom_view.png") == CATEGORY_BATHROOM
    assert classify_by_filename("12_bedroom.jpg") == CATEGORY_BEDROOM
    assert classify_by_filename("12_frontal.jpg") == CATEGORY_EXTERIOR
    assert classify_by_filename("living_room.jpeg") == CATEGORY_LIVING
    assert classify_by_filename("fine_dining.jpg") == CATEGORY_DINING
    assert classify_by_filename("indoor_swimming_pool.jpg") == CATEGORY_POOL
    assert classify_by_filename("covered_parking.jpg") == CATEGORY_PARKING

    # Random / uninformative filenames return None in Step 1
    assert classify_by_filename("IMG_2041.jpg") is None
    assert classify_by_filename("photo1.jpg") is None
    assert classify_by_filename("dsc0029.png") is None


def test_step2_vision_llm_fallback(tmp_path: Path):
    """Step 2: When filename is generic, use Vision LLM fallback."""
    from PIL import Image

    dummy_img = tmp_path / "IMG_9999.jpg"
    im = Image.new("RGB", (640, 480), color=(100, 150, 200))
    im.save(dummy_img)

    # Mock Vision LLM response
    with patch("propvid.vision.classify_with_vision_llm", return_value=CATEGORY_KITCHEN):
        category = classify_image(dummy_img)
        assert category == CATEGORY_KITCHEN


def test_content_to_photo_matching_prevents_bathroom_on_kitchen():
    """Crucial requirement: Washroom photo MUST NOT be shown during kitchen voiceover."""
    valid_images = [
        ValidImage(path=Path("/tmp/12_bathroom.jpg"), width=1280, height=720),
        ValidImage(path=Path("/tmp/12_bedroom.jpg"), width=1280, height=720),
        ValidImage(path=Path("/tmp/12_frontal.jpg"), width=1280, height=720),
        ValidImage(path=Path("/tmp/12_kitchen.jpg"), width=1280, height=720),
        ValidImage(path=Path("/tmp/13_frontal.jpg"), width=1280, height=720),
    ]

    scenes = [
        SceneSpec(id="title_0", kind="title", headline="Humangasorous heights", caption="Noida", narration="Welcome to Humangasorous heights."),
        SceneSpec(id="feature_1", kind="feature", headline="Culinary Elegance", caption="Modular Kitchen", narration="Step into the sleek modular kitchen."),
        SceneSpec(id="feature_2", kind="feature", headline="Fine Dining", caption="Fine-Dining station", narration="Host elegant dinners here."),
        SceneSpec(id="feature_3", kind="feature", headline="Spa Retreat", caption="Designer Washrooms", narration="Relax in the designer washrooms."),
        SceneSpec(id="cta_final", kind="cta", headline="Contact Us", caption="Call today", narration="Call today to book."),
    ]

    matches = match_scenes_to_images(scenes, valid_images)
    scene_map = {scene.id: img_path.name for scene, img_path, idx in matches}

    # Kitchen scene MUST get the kitchen photo
    assert scene_map["feature_1"] == "12_kitchen.jpg"
    # Washroom scene MUST get the bathroom photo
    assert scene_map["feature_3"] == "12_bathroom.jpg"
    # Kitchen scene must NEVER get bathroom
    assert scene_map["feature_1"] != "12_bathroom.jpg"
    # Title gets frontal/exterior
    assert "frontal" in scene_map["title_0"]
