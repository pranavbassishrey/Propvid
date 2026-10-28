"""Unit tests for LLM script polish, caching, and fact-checking reversion."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from propvid.config import Settings
from propvid.schema import PropertyInput
from propvid.scriptgen import generate_script
from propvid.scriptgen.llm import polish_script_with_llm
from propvid.scriptgen.template import build_template_script


@pytest.fixture
def sample_property() -> PropertyInput:
    return PropertyInput(
        name="Skyline Vista",
        location="Indiranagar, Bengaluru",
        price="₹1.25 Cr",
        property_type="3 BHK Luxury Apartment",
        tone="premium",
        features=["Italian marble flooring", "East-facing balcony", "Modular kitchen"],
        images=[
            {"path": "examples/images/sample1.jpg", "label": "Living Room"},
            {"path": "examples/images/sample2.jpg", "label": "Balcony"},
        ],
        contact={"name": "Sarah Rao", "phone": "+91 98765 43210"},
        cta="Schedule a Private Tour",
    )


def test_llm_mode_off(sample_property):
    template = build_template_script(sample_property)
    script, report = generate_script(sample_property, llm_mode="off")
    assert not report.llm_used
    assert script.model_dump() == template.model_dump()


def test_llm_no_api_key(sample_property, tmp_path):
    settings = Settings(openrouter_api_key=None, cache_dir=tmp_path / "cache")
    template = build_template_script(sample_property)
    script, report = polish_script_with_llm(sample_property, template, settings=settings)
    assert not report.llm_used
    assert "No OpenRouter API key" in (report.error or "")
    assert script.model_dump() == template.model_dump()


def test_llm_successful_polish_and_caching(sample_property, tmp_path):
    cache_dir = tmp_path / "cache"
    settings = Settings(
        openrouter_api_key="test_key",
        openrouter_models=["nvidia/nemotron-3.5-super-vl:free"],
        cache_dir=cache_dir,
    )
    template = build_template_script(sample_property)

    llm_response_json = {
        "id": "gen-12345",
        "model": "nvidia/nemotron-3.5-super-vl:free",
        "usage": {"prompt_tokens": 150, "completion_tokens": 80, "total_tokens": 230},
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "scenes": [
                            {
                                "id": template.scenes[0].id,
                                "kind": "title",
                                "headline": "Skyline Vista Indiranagar",
                                "caption": "3 BHK Luxury Apartment ₹1.25 Cr",
                                "narration": "Welcome to Skyline Vista in Bengaluru.",
                            },
                            {
                                "id": template.scenes[1].id,
                                "kind": "feature",
                                "headline": "Refined Interiors",
                                "caption": "Italian marble flooring",
                                "narration": "This residence includes Italian marble flooring.",
                            },
                        ]
                    })
                }
            }
        ],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = llm_response_json

    # First call: network mock
    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        script, report = polish_script_with_llm(sample_property, template, settings=settings)
        assert mock_post.call_count == 1
        assert report.llm_used
        assert not report.cache_hit
        assert report.model_used == "nvidia/nemotron-3.5-super-vl:free"
        assert report.tokens["total_tokens"] == 230
        assert script.scenes[0].narration == "Welcome to Skyline Vista in Bengaluru."

    # Cache file should now exist on disk
    cache_files = list(cache_dir.glob("*.json"))
    assert len(cache_files) == 1

    # Second call: must hit cache with 0 network calls
    with patch("httpx.Client.post") as mock_post2:
        script2, report2 = polish_script_with_llm(sample_property, template, settings=settings)
        assert mock_post2.call_count == 0
        assert report2.llm_used
        assert report2.cache_hit
        assert report2.model_used == "nvidia/nemotron-3.5-super-vl:free"
        assert script2.scenes[0].narration == "Welcome to Skyline Vista in Bengaluru."


def test_llm_hallucination_reverts_specific_scene(sample_property, tmp_path):
    cache_dir = tmp_path / "cache"
    settings = Settings(
        openrouter_api_key="test_key",
        openrouter_models=["nvidia/nemotron-3.5-super-vl:free"],
        cache_dir=cache_dir,
    )
    template = build_template_script(sample_property)

    # Scene 1 has valid polish.
    # Scene 2 has an invented number "999" and a banned phrase "cheapest".
    llm_response_json = {
        "model": "nvidia/nemotron-3.5-super-vl:free",
        "usage": {"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180},
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "scenes": [
                            {
                                "id": template.scenes[0].id,
                                "kind": "title",
                                "headline": "Skyline Vista",
                                "caption": "Indiranagar, Bengaluru",
                                "narration": "Welcome to Skyline Vista in Bengaluru.",
                            },
                            {
                                "id": template.scenes[1].id,
                                "kind": "feature",
                                "headline": "Cheapest Home",
                                "caption": "Only 999 gold coins",
                                "narration": "Enjoy the cheapest residence with 999 luxuries.",
                            },
                        ]
                    })
                }
            }
        ],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = llm_response_json

    with patch("httpx.Client.post", return_value=mock_resp):
        script, report = polish_script_with_llm(sample_property, template, settings=settings)
        assert report.llm_used
        # Scene 0 accepted
        assert script.scenes[0].narration == "Welcome to Skyline Vista in Bengaluru."
        # Scene 1 rejected and reverted to template
        assert template.scenes[1].id in report.reverted_scenes
        assert script.scenes[1].narration == template.scenes[1].narration
        assert "999" not in script.scenes[1].narration


def test_llm_network_error_falls_back_gracefully(sample_property, tmp_path):
    settings = Settings(
        openrouter_api_key="test_key",
        openrouter_models=["nvidia/nemotron-3.5-super-vl:free"],
        cache_dir=tmp_path / "cache",
    )
    template = build_template_script(sample_property)

    mock_resp = MagicMock()
    mock_resp.status_code = 502
    mock_resp.text = "Bad Gateway"

    with patch("httpx.Client.post", return_value=mock_resp):
        script, report = polish_script_with_llm(sample_property, template, settings=settings)
        assert not report.llm_used
        assert "HTTP 502" in (report.error or "")
        # Script matches template
        assert script.model_dump() == template.model_dump()


def test_llm_malformed_json_falls_back_gracefully(sample_property, tmp_path):
    settings = Settings(
        openrouter_api_key="test_key",
        openrouter_models=["nvidia/nemotron-3.5-super-vl:free"],
        cache_dir=tmp_path / "cache",
    )
    template = build_template_script(sample_property)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Here is your script: { incomplete json"}}]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        script, report = polish_script_with_llm(sample_property, template, settings=settings)
        assert not report.llm_used
        assert "Malformed JSON" in (report.error or "")
        assert script.model_dump() == template.model_dump()
