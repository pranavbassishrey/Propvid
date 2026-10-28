"""Tests for fact verification and banned-phrase detection."""

from propvid.inputs import load_property
from propvid.schema import SceneSpec
from propvid.scriptgen.template import build_template_script
from propvid.scriptgen.verify import verify_scene


def test_verify_passes_on_template_scenes():
    """Verify all template-generated scenes pass verification without violations."""
    prop, _ = load_property("examples/property.sample.json")
    script = build_template_script(prop)

    for scene in script.scenes:
        violations = verify_scene(scene, prop)
        assert violations == [], f"Unexpected violations in scene {scene.id}: {violations}"


def test_verify_catches_invented_number():
    """Verify an unbacked number triggers a violation."""
    prop, _ = load_property("examples/property.sample.json")
    bad_scene = SceneSpec(
        id="feature_bad",
        kind="feature",
        headline="Exclusive Units",
        caption="Only 4 units left",
        narration="Act fast because only 4 units remain available.",
    )
    violations = verify_scene(bad_scene, prop)
    assert any("Invented number" in v and "4" in v for v in violations)


def test_verify_catches_invented_proper_noun():
    """Verify invented locations or entities trigger violations."""
    prop, _ = load_property("examples/property.sample.json")
    bad_scene = SceneSpec(
        id="feature_bad",
        kind="feature",
        headline="Great Connectivity",
        caption="Convenient Travel",
        narration="Conveniently situated opposite Cambridge University campus.",
    )
    violations = verify_scene(bad_scene, prop)
    assert any("Invented entity" in v and "Cambridge" in v for v in violations)


def test_verify_catches_banned_phrases():
    """Verify banned phrases like 'best' and 'near' trigger violations."""
    prop, _ = load_property("examples/property.sample.json")
    scene_with_best = SceneSpec(
        id="f1",
        kind="feature",
        headline="Quality",
        caption="High standard",
        narration="This is the best apartment in the entire region.",
    )
    violations = verify_scene(scene_with_best, prop)
    assert any("banned phrase" in v and "best" in v for v in violations)

    scene_with_near = SceneSpec(
        id="f2",
        kind="feature",
        headline="Location",
        caption="Location",
        narration="Located near the commercial tech hub.",
    )
    violations = verify_scene(scene_with_near, prop)
    assert any("banned phrase" in v and "near" in v for v in violations)


def test_verify_banned_phrase_word_boundaries():
    """Verify word boundaries prevent false positives for 'nearly' and 'Westbest'."""
    prop, _ = load_property("examples/property.sample.json")

    # 'nearly' contains 'near' as substring, but is NOT the word 'near'
    scene_nearly = SceneSpec(
        id="f_nearly",
        kind="feature",
        headline="Spacious Design",
        caption="Modern layout",
        narration="The construction is nearly completed with fine finishes.",
    )
    violations_nearly = verify_scene(scene_nearly, prop)
    assert not any("banned phrase" in v and "near" in v for v in violations_nearly)

    # 'Westbest' contains 'best' as substring, but is NOT the word 'best'
    scene_westbest = SceneSpec(
        id="f_westbest",
        kind="feature",
        headline="Crafted Materials",
        caption="Quality build",
        narration="Fitted with Westbest architectural fixtures.",
    )
    violations_westbest = verify_scene(scene_westbest, prop)
    assert not any("banned phrase" in v and "best" in v for v in violations_westbest)
    assert not any("banned phrase" in v for v in violations_westbest)


def test_verify_share_copy():
    """Verify social share copy and hashtag auditing."""
    from propvid.scriptgen.verify import verify_share_copy
    prop, _ = load_property("examples/property.sample.json")

    valid_copy = (
        "Discover Green Valley Heights - 2-BHK Apartment in Whitefield, Bengaluru offered at ₹1.25 Cr. "
        "Highlights include Modular kitchen. Book your site visit today!\n\n"
        "#2BHKApartment #Whitefield #Bengaluru #RealEstate #PropertyForSale"
    )
    assert verify_share_copy(valid_copy, prop) == []

    bad_copy = (
        "Discover Green Valley Heights! Best apartment with guaranteed returns. Only 99 units left! #BillionaireLifestyle"
    )
    violations = verify_share_copy(bad_copy, prop)
    assert any("Banned phrase" in v and "best" in v for v in violations)
    assert any("Banned phrase" in v and "guaranteed" in v for v in violations)
    assert any("Invented number" in v and "99" in v for v in violations)
    assert any("Unverified hashtag" in v for v in violations)




def test_verify_length_limits():
    """Verify narration > 22 words or caption > 8 words triggers violation."""
    prop, _ = load_property("examples/property.sample.json")
    long_narration = "word " * 25
    bad_narration_scene = SceneSpec(
        id="long_n",
        kind="feature",
        headline="Spacious Living",
        caption="Modern living",
        narration=long_narration.strip(),
    )
    violations = verify_scene(bad_narration_scene, prop)
    assert any("Narration exceeds 22 words" in v for v in violations)

    bad_caption_scene = SceneSpec(
        id="long_c",
        kind="feature",
        headline="Spacious Living",
        caption="This is a very unnecessarily long caption exceeding eight words",
        narration="Features include modular kitchen.",
    )
    violations_cap = verify_scene(bad_caption_scene, prop)
    assert any("Caption exceeds 8 words" in v for v in violations_cap)
