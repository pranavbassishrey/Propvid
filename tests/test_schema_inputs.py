"""Tests for schema validation, input loading, image checking, and CLI subprocess execution."""

import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from PIL import Image, ImageOps

from propvid.errors import InputError
from propvid.inputs import check_images, load_property
from propvid.schema import ImageRef, PropertyInput


def test_load_sample_property():
    """Verify loading the full sample property specification."""
    sample_path = Path("examples/property.sample.json")
    prop, base_dir = load_property(sample_path)
    assert prop.name == "Green Valley Heights"
    assert prop.location == "Whitefield, Bengaluru"
    assert prop.price == "₹1.25 Cr"
    assert prop.property_type == "2-BHK Apartment"
    assert len(prop.features) == 5
    assert prop.tone == "warm"
    assert prop.contact is not None
    assert prop.contact.name == "Asha Rao"

    # Verify images check passes with valid images
    valid_images = check_images(prop.images, base_dir)
    assert len(valid_images) == 6


def test_load_minimal_property_defaults():
    """Verify loading minimal property specification checks defaults correctly."""
    minimal_path = Path("examples/property.minimal.json")
    prop, base_dir = load_property(minimal_path)
    assert prop.name == "Skyline Residency"
    assert prop.location == "Indiranagar, Bengaluru"
    assert prop.price == "₹2.10 Cr"
    assert prop.property_type == "3-BHK Penthouse"
    assert prop.features == []
    assert prop.contact is None
    assert prop.cta == "Enquire today"
    assert prop.tone == "warm"

    valid_images = check_images(prop.images, base_dir)
    assert len(valid_images) == 2


def test_load_broken_images_example(caplog):
    """Verify property with broken images logs warnings but retains valid images."""
    broken_images_path = Path("examples/property.broken_images.json")
    prop, base_dir = load_property(broken_images_path)

    with caplog.at_level("WARNING"):
        valid_images = check_images(prop.images, base_dir)

    assert len(valid_images) == 2
    log_text = caplog.text
    assert "Image file does not exist, skipping" in log_text
    assert "Corrupted or unreadable image file, skipping" in log_text
    assert "smaller than minimum required" in log_text


def test_missing_single_required_field(tmp_path: Path):
    """Verify missing 'name' field raises InputError listing the missing field."""
    bad_data = {
        "location": "Bengaluru",
        "price": "₹1 Cr",
        "property_type": "Villa",
    }
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad_data), encoding="utf-8")

    with pytest.raises(InputError) as exc_info:
        load_property(p)
    assert "Missing required property field(s)" in str(exc_info.value)
    assert "'name'" in str(exc_info.value)


def test_missing_multiple_required_fields(tmp_path: Path):
    """Verify all missing required fields are collected and reported in one InputError."""
    bad_data = {
        "price": "₹1 Cr",
    }
    p = tmp_path / "bad_multiple.json"
    p.write_text(json.dumps(bad_data), encoding="utf-8")

    with pytest.raises(InputError) as exc_info:
        load_property(p)
    err = str(exc_info.value)
    assert "'name'" in err
    assert "'location'" in err
    assert "'property_type'" in err
    assert "'price'" not in err


def test_empty_or_whitespace_name_counts_as_missing(tmp_path: Path):
    """Verify whitespace-only or empty name counts as missing required field."""
    bad_data = {
        "name": "   ",
        "location": "Bengaluru",
        "price": "₹1 Cr",
        "property_type": "Villa",
    }
    p = tmp_path / "whitespace_name.json"
    p.write_text(json.dumps(bad_data), encoding="utf-8")

    with pytest.raises(InputError) as exc_info:
        load_property(p)
    assert "'name'" in str(exc_info.value)


def test_features_longer_than_12_rejected(tmp_path: Path):
    """Verify more than 12 features is rejected with an InputError."""
    data = {
        "name": "Luxury Estate",
        "location": "Mumbai",
        "price": "₹5 Cr",
        "property_type": "Villa",
        "features": [f"Feature {i}" for i in range(13)],  # 13 items > 12
    }
    p = tmp_path / "too_many_features.json"
    p.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(InputError) as exc_info:
        load_property(p)
    assert "features" in str(exc_info.value).lower()


def test_invalid_tone_rejected(tmp_path: Path):
    """Verify unrecognized tone is rejected."""
    data = {
        "name": "Luxury Estate",
        "location": "Mumbai",
        "price": "₹5 Cr",
        "property_type": "Villa",
        "tone": "comedic",
    }
    p = tmp_path / "invalid_tone.json"
    p.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(InputError) as exc_info:
        load_property(p)
    assert "tone" in str(exc_info.value).lower()


def test_price_preserved_exactly_as_string(tmp_path: Path):
    """Verify price formatting and rupee symbol are strictly preserved."""
    exact_price = "₹1.25 Cr"
    data = {
        "name": "Green Valley",
        "location": "Whitefield",
        "price": exact_price,
        "property_type": "Apartment",
    }
    p = tmp_path / "price_check.json"
    p.write_text(json.dumps(data), encoding="utf-8")

    prop, _ = load_property(p)
    assert prop.price == exact_price


def test_broken_property_file_exits():
    """Verify broken property example fails validation with missing name."""
    broken_path = Path("examples/property.broken.json")
    with pytest.raises(InputError) as exc_info:
        load_property(broken_path)
    assert "'name'" in str(exc_info.value)


def test_invalid_json(tmp_path: Path):
    """Verify invalid JSON syntax raises clear InputError."""
    p = tmp_path / "invalid.json"
    p.write_text("{ broken json: true", encoding="utf-8")
    with pytest.raises(InputError) as exc_info:
        load_property(p)
    assert "Invalid JSON" in str(exc_info.value)


def test_nonexistent_file():
    """Verify non-existent path raises InputError."""
    with pytest.raises(InputError) as exc_info:
        load_property("nonexistent_path_to_file.json")
    assert "not found" in str(exc_info.value)


def test_missing_image_file_warning(tmp_path: Path, caplog):
    """Verify a missing image file distinctly logs a missing warning."""
    missing_path = tmp_path / "does_not_exist.jpg"
    images = [
        ImageRef(path=str(missing_path)),
        ImageRef(path="examples/images/01_exterior.jpg"),
    ]

    with caplog.at_level("WARNING"):
        valid = check_images(images, base_dir=Path("."))

    assert len(valid) == 1
    assert "Image file does not exist, skipping" in caplog.text


def test_zero_valid_images_raises(tmp_path: Path):
    """Verify zero valid images raises InputError."""
    corrupt_path = tmp_path / "corrupt.jpg"
    corrupt_path.write_bytes(b"garbage")

    images = [ImageRef(path=str(corrupt_path))]
    with pytest.raises(InputError) as exc_info:
        check_images(images, base_dir=tmp_path)
    assert "Zero valid images found" in str(exc_info.value)


def test_exif_rotated_image_comes_out_upright(tmp_path: Path):
    """Verify EXIF-rotated images are properly oriented by check_images."""
    # Create image with width=1000, height=800 and EXIF orientation=6 (rotate 90 CW)
    img = Image.new("RGB", (1000, 800), color=(100, 150, 200))
    exif = img.getexif()
    exif[0x0112] = 6  # Orientation tag 6
    test_img_path = tmp_path / "exif_rotated.jpg"
    img.save(test_img_path, exif=exif)

    valid_images = check_images([ImageRef(path=str(test_img_path))], base_dir=tmp_path)
    assert len(valid_images) == 1
    # Once transposed upright, width should be 800 and height should be 1000
    assert valid_images[0].width == 800
    assert valid_images[0].height == 1000



def test_cli_subprocess_exit_codes():
    """Verify CLI exit codes via real subprocess: 0 for valid, 2 for broken."""
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    # Valid run -> exit 0
    res_valid = subprocess.run(
        [sys.executable, "-m", "propvid", "validate", "-i", "examples/property.sample.json"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert res_valid.returncode == 0
    assert "[OK]" in res_valid.stdout

    # Broken run -> exit 2
    res_broken = subprocess.run(
        [sys.executable, "-m", "propvid", "validate", "-i", "examples/property.broken.json"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert res_broken.returncode == 2
    assert "Error: Missing required property field(s): 'name'" in res_broken.stderr


def test_cli_windows_console_safety_cp1252():
    """Verify validate succeeds under cp1252 console encoding without encoding crashes."""
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    env["PYTHONIOENCODING"] = "cp1252"

    res = subprocess.run(
        [sys.executable, "-m", "propvid", "validate", "-i", "examples/property.sample.json"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert res.returncode == 0
    assert "Traceback" not in res.stderr
    assert "[OK]" in res.stdout
