import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from smallworld_api.services.preview_enhancement import (
    DEFAULT_CREATIVE_PROMPT,
    DEFAULT_GEMINI_IMAGE_MODEL,
    SYSTEM_ENHANCEMENT_PROMPT,
    EnhancementError,
    build_enhancement_prompt,
    enhance_preview,
)


def test_build_enhancement_prompt_with_dynamic_prompt():
    result = build_enhancement_prompt("Snowy winter scene, overcast sky")
    assert result.startswith(SYSTEM_ENHANCEMENT_PROMPT)
    assert "\n\n---\n\n" in result
    assert result.endswith("Snowy winter scene, overcast sky")


def test_build_enhancement_prompt_without_prompt():
    result = build_enhancement_prompt(None)
    assert result.startswith(SYSTEM_ENHANCEMENT_PROMPT)
    assert result.endswith(DEFAULT_CREATIVE_PROMPT)


def test_build_enhancement_prompt_with_empty_string():
    result = build_enhancement_prompt("")
    assert result.startswith(SYSTEM_ENHANCEMENT_PROMPT)
    assert result.endswith(DEFAULT_CREATIVE_PROMPT)


@pytest.mark.asyncio
async def test_enhance_preview_remaps_legacy_model_and_writes_image(tmp_path: Path):
    raw_image_path = tmp_path / "raw.png"
    output_path = tmp_path / "enhanced.png"
    raw_image_path.write_bytes(b"raw-bytes")

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": base64.b64encode(b"enhanced-bytes").decode(),
                            }
                        }
                    ]
                }
            }
        ]
    }

    client = AsyncMock()
    client.post.return_value = response
    client_context = AsyncMock()
    client_context.__aenter__.return_value = client
    client_context.__aexit__.return_value = None

    with patch(
        "smallworld_api.services.preview_enhancement.httpx.AsyncClient",
        return_value=client_context,
    ):
        result = await enhance_preview(
            raw_image_path=raw_image_path,
            output_path=output_path,
            prompt="Enhance this preview.",
            api_key="test-key",
            model="gemini-2.0-flash-exp-image-generation",
        )

    assert result.model_used == DEFAULT_GEMINI_IMAGE_MODEL
    assert output_path.read_bytes() == b"enhanced-bytes"

    post_call = client.post.await_args
    assert DEFAULT_GEMINI_IMAGE_MODEL in post_call.args[0]
    assert post_call.kwargs["json"] == {
        "contents": [
            {
                "parts": [
                    {"text": "Enhance this preview."},
                    {
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": base64.b64encode(b"raw-bytes").decode(),
                        }
                    },
                ]
            }
        ]
    }


@pytest.mark.asyncio
async def test_enhance_preview_includes_gemini_error_details(tmp_path: Path):
    raw_image_path = tmp_path / "raw.png"
    raw_image_path.write_bytes(b"raw-bytes")

    request = httpx.Request(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/models/test:generateContent",
    )
    response = httpx.Response(
        400,
        request=request,
        json={"error": {"message": "Invalid image request"}},
    )

    client = AsyncMock()
    client.post.return_value = response
    client_context = AsyncMock()
    client_context.__aenter__.return_value = client
    client_context.__aexit__.return_value = None

    with (
        patch(
            "smallworld_api.services.preview_enhancement.httpx.AsyncClient",
            return_value=client_context,
        ),
        pytest.raises(
            EnhancementError,
            match="Gemini API returned 400: Invalid image request",
        ),
    ):
        await enhance_preview(
            raw_image_path=raw_image_path,
            output_path=tmp_path / "enhanced.png",
            prompt="Enhance this preview.",
            api_key="test-key",
            model=DEFAULT_GEMINI_IMAGE_MODEL,
        )
