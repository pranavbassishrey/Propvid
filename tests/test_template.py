"""Tests for deterministic template script generation."""

from propvid.inputs import load_property
from propvid.schema import Contact, PropertyInput
from propvid.scriptgen.template import build_template_script


def test_template_script_full_sample():
    """Verify template script generates title, up to 5 features, and CTA."""
    prop, _ = load_property("examples/property.sample.json")
    script = build_template_script(prop)

    assert script.source == "template"
    # Title + 5 features + CTA = 7 scenes
    assert len(script.scenes) == 7
    assert script.scenes[0].kind == "title"
    assert script.scenes[0].headline == prop.name
    assert prop.location in script.scenes[0].caption
    assert prop.price in script.scenes[0].caption

    for idx, feat in enumerate(prop.features[:5]):
        scene = script.scenes[idx + 1]
        assert scene.kind == "feature"
        assert scene.headline == feat
        assert feat in scene.narration

    cta_scene = script.scenes[-1]
    assert cta_scene.kind == "cta"
    assert cta_scene.headline == prop.cta
    assert prop.contact.name in cta_scene.narration
    assert prop.contact.phone in cta_scene.narration


def test_template_script_no_features_creates_highlight():
    """Verify property without features generates a highlight scene."""
    prop, _ = load_property("examples/property.minimal.json")
    script = build_template_script(prop)

    # Title + 1 highlight + CTA = 3 scenes
    assert len(script.scenes) == 3
    assert script.scenes[0].kind == "title"
    assert script.scenes[1].kind == "highlight"
    assert script.scenes[1].headline == prop.property_type
    assert prop.location in script.scenes[1].caption
    assert prop.property_type in script.scenes[1].narration
    assert script.scenes[2].kind == "cta"


def test_template_script_no_contact():
    """Verify CTA without contact shows only CTA text."""
    prop = PropertyInput(
        name="Sun City",
        location="Pune",
        price="₹75 L",
        property_type="1-BHK",
        contact=None,
        cta="Book now",
    )
    script = build_template_script(prop)
    cta_scene = script.scenes[-1]
    assert cta_scene.caption == "Book now"
    assert cta_scene.narration == "Book now."


def test_tone_to_direction_mapping():
    """Verify tone maps cleanly to scene direction."""
    base_data = {
        "name": "Skyline",
        "location": "Mumbai",
        "price": "₹3 Cr",
        "property_type": "Penthouse",
    }
    for tone, expected_dir in [("warm", "warm"), ("premium", "calm"), ("energetic", "excited")]:
        prop = PropertyInput(**base_data, tone=tone)
        script = build_template_script(prop)
        assert script.scenes[0].direction == expected_dir
