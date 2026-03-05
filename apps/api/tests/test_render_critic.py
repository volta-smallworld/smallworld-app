import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from smallworld_api.services.render_critic import (
    MAX_ALT_DELTA,
    MAX_FOV_DELTA,
    MAX_HEADING_DELTA,
    MAX_PITCH_DELTA,
    CritiqueError,
    CritiqueNotConfiguredError,
    CritiqueResult,
    _clamp,
    _select_model,
    critique_render,
)


@pytest.mark.asyncio
async def test_missing_api_key_raises_not_configured(tmp_path: Path):
    """Missing API key raises CritiqueNotConfiguredError."""
    raw = tmp_path / "raw.png"
    raw.write_bytes(b"fake-png")

    with pytest.raises(CritiqueNotConfiguredError, match="GEMINI_API_KEY"):
        await critique_render(
            raw_image_path=raw,
            iteration=1,
            api_key="",
            fast_model="gemini-2.0-flash",
            smart_model="gemini-2.5-flash",
            threshold=75.0,
        )


def test_select_model_fast_for_iterations_1_and_2():
    assert _select_model(1, "fast", "smart") == "fast"
    assert _select_model(2, "fast", "smart") == "fast"


def test_select_model_smart_for_iteration_3():
    assert _select_model(3, "fast", "smart") == "smart"


def test_clamp_within_bounds():
    assert _clamp(5.0, 15.0) == 5.0
    assert _clamp(-5.0, 15.0) == -5.0


def test_clamp_exceeds_bounds():
    assert _clamp(20.0, 15.0) == 15.0
    assert _clamp(-20.0, 15.0) == -15.0


def _make_gemini_response(scores: dict) -> MagicMock:
    """Build a mock Gemini response with structured JSON output."""
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": json.dumps(scores)}
                    ]
                }
            }
        ]
    }
    return response


@pytest.mark.asyncio
async def test_valid_response_parsed_into_result(tmp_path: Path):
    raw = tmp_path / "raw.png"
    raw.write_bytes(b"fake-png")

    scores = {
        "overall_score": 82,
        "composition_score": 85,
        "exposure_score": 78,
        "terrain_visibility_score": 80,
        "aesthetic_score": 84,
        "reasoning": "Good composition but slightly underexposed.",
        "heading_delta": 5.0,
        "pitch_delta": -2.0,
        "alt_delta": 50.0,
        "fov_delta": 0.0,
    }

    response = _make_gemini_response(scores)
    client = AsyncMock()
    client.post.return_value = response
    client_context = AsyncMock()
    client_context.__aenter__.return_value = client
    client_context.__aexit__.return_value = None

    with patch(
        "smallworld_api.services.render_critic.httpx.AsyncClient",
        return_value=client_context,
    ):
        result = await critique_render(
            raw_image_path=raw,
            iteration=1,
            api_key="test-key",
            fast_model="gemini-2.0-flash",
            smart_model="gemini-2.5-flash",
            threshold=75.0,
        )

    assert isinstance(result, CritiqueResult)
    assert result.overall_score == 82
    assert result.composition_score == 85
    assert result.exposure_score == 78
    assert result.terrain_visibility_score == 80
    assert result.aesthetic_score == 84
    assert result.reasoning == "Good composition but slightly underexposed."
    assert result.pose_adjustment["heading_delta"] == 5.0
    assert result.pose_adjustment["pitch_delta"] == -2.0
    assert result.pose_adjustment["alt_delta"] == 50.0
    assert result.pose_adjustment["fov_delta"] == 0.0
    assert result.accepted is True
    assert result.model_used == "gemini-2.0-flash"
    assert result.iteration == 1


@pytest.mark.asyncio
async def test_score_below_threshold_not_accepted(tmp_path: Path):
    raw = tmp_path / "raw.png"
    raw.write_bytes(b"fake-png")

    scores = {
        "overall_score": 60,
        "composition_score": 55,
        "exposure_score": 65,
        "terrain_visibility_score": 58,
        "aesthetic_score": 62,
        "reasoning": "Poor framing.",
        "heading_delta": 10.0,
        "pitch_delta": 5.0,
        "alt_delta": 100.0,
        "fov_delta": 3.0,
    }

    response = _make_gemini_response(scores)
    client = AsyncMock()
    client.post.return_value = response
    client_context = AsyncMock()
    client_context.__aenter__.return_value = client
    client_context.__aexit__.return_value = None

    with patch(
        "smallworld_api.services.render_critic.httpx.AsyncClient",
        return_value=client_context,
    ):
        result = await critique_render(
            raw_image_path=raw,
            iteration=1,
            api_key="test-key",
            fast_model="gemini-2.0-flash",
            smart_model="gemini-2.5-flash",
            threshold=75.0,
        )

    assert result.accepted is False
    assert result.overall_score == 60


@pytest.mark.asyncio
async def test_deltas_clamped_to_max_bounds(tmp_path: Path):
    raw = tmp_path / "raw.png"
    raw.write_bytes(b"fake-png")

    scores = {
        "overall_score": 50,
        "composition_score": 50,
        "exposure_score": 50,
        "terrain_visibility_score": 50,
        "aesthetic_score": 50,
        "reasoning": "Bad render.",
        "heading_delta": 30.0,
        "pitch_delta": -25.0,
        "alt_delta": 500.0,
        "fov_delta": -10.0,
    }

    response = _make_gemini_response(scores)
    client = AsyncMock()
    client.post.return_value = response
    client_context = AsyncMock()
    client_context.__aenter__.return_value = client
    client_context.__aexit__.return_value = None

    with patch(
        "smallworld_api.services.render_critic.httpx.AsyncClient",
        return_value=client_context,
    ):
        result = await critique_render(
            raw_image_path=raw,
            iteration=1,
            api_key="test-key",
            fast_model="gemini-2.0-flash",
            smart_model="gemini-2.5-flash",
            threshold=75.0,
        )

    assert result.pose_adjustment["heading_delta"] == MAX_HEADING_DELTA
    assert result.pose_adjustment["pitch_delta"] == -MAX_PITCH_DELTA
    assert result.pose_adjustment["alt_delta"] == MAX_ALT_DELTA
    assert result.pose_adjustment["fov_delta"] == -MAX_FOV_DELTA


@pytest.mark.asyncio
async def test_iteration_3_uses_smart_model(tmp_path: Path):
    raw = tmp_path / "raw.png"
    raw.write_bytes(b"fake-png")

    scores = {
        "overall_score": 90,
        "composition_score": 88,
        "exposure_score": 92,
        "terrain_visibility_score": 91,
        "aesthetic_score": 89,
        "reasoning": "Excellent render.",
        "heading_delta": 0,
        "pitch_delta": 0,
        "alt_delta": 0,
        "fov_delta": 0,
    }

    response = _make_gemini_response(scores)
    client = AsyncMock()
    client.post.return_value = response
    client_context = AsyncMock()
    client_context.__aenter__.return_value = client
    client_context.__aexit__.return_value = None

    with patch(
        "smallworld_api.services.render_critic.httpx.AsyncClient",
        return_value=client_context,
    ):
        result = await critique_render(
            raw_image_path=raw,
            iteration=3,
            api_key="test-key",
            fast_model="gemini-2.0-flash",
            smart_model="gemini-2.5-flash",
            threshold=75.0,
        )

    assert result.model_used == "gemini-2.5-flash"

    # Verify the URL contains the smart model
    post_call = client.post.await_args
    assert "gemini-2.5-flash" in post_call.args[0]


@pytest.mark.asyncio
async def test_http_error_raises_critique_error(tmp_path: Path):
    raw = tmp_path / "raw.png"
    raw.write_bytes(b"fake-png")

    request = httpx.Request(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/models/test:generateContent",
    )
    response = httpx.Response(
        429,
        request=request,
        json={"error": {"message": "Rate limit exceeded"}},
    )

    client = AsyncMock()
    client.post.return_value = response
    client_context = AsyncMock()
    client_context.__aenter__.return_value = client
    client_context.__aexit__.return_value = None

    with (
        patch(
            "smallworld_api.services.render_critic.httpx.AsyncClient",
            return_value=client_context,
        ),
        pytest.raises(
            CritiqueError,
            match="Gemini critique API returned 429: Rate limit exceeded",
        ),
    ):
        await critique_render(
            raw_image_path=raw,
            iteration=1,
            api_key="test-key",
            fast_model="gemini-2.0-flash",
            smart_model="gemini-2.5-flash",
            threshold=75.0,
        )


@pytest.mark.asyncio
async def test_malformed_response_raises_critique_error(tmp_path: Path):
    raw = tmp_path / "raw.png"
    raw.write_bytes(b"fake-png")

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"candidates": [{"content": {"parts": []}}]}

    client = AsyncMock()
    client.post.return_value = response
    client_context = AsyncMock()
    client_context.__aenter__.return_value = client
    client_context.__aexit__.return_value = None

    with (
        patch(
            "smallworld_api.services.render_critic.httpx.AsyncClient",
            return_value=client_context,
        ),
        pytest.raises(CritiqueError, match="Failed to parse critique response"),
    ):
        await critique_render(
            raw_image_path=raw,
            iteration=1,
            api_key="test-key",
            fast_model="gemini-2.0-flash",
            smart_model="gemini-2.5-flash",
            threshold=75.0,
        )
