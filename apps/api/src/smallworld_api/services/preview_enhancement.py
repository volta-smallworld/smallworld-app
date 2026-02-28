"""Gemini image-editing enhancement for preview renders."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

DEFAULT_ENHANCEMENT_PROMPT = (
    "Ultra-realistic landscape photograph, golden hour lighting, "
    "85mm lens, high dynamic range, cinematic color grading."
)


@dataclass
class EnhancementResult:
    image_path: Path
    model_used: str


class EnhancementError(Exception):
    """Raised when enhancement fails."""


class EnhancementNotConfiguredError(Exception):
    """Raised when enhancement is not configured."""


async def enhance_preview(
    *,
    raw_image_path: Path,
    output_path: Path,
    prompt: str,
    api_key: str,
    model: str,
    timeout_seconds: int = 60,
) -> EnhancementResult:
    if not api_key:
        raise EnhancementNotConfiguredError("GEMINI_API_KEY is not set")
    if not model:
        raise EnhancementNotConfiguredError("GEMINI_IMAGE_MODEL is not set")

    raw_bytes = raw_image_path.read_bytes()
    b64_image = base64.b64encode(raw_bytes).decode()

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent?key={api_key}"
    )

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": b64_image,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
            "responseMimeType": "image/png",
        },
    }

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        try:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise EnhancementError(
                f"Gemini API returned {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise EnhancementError(f"Gemini API request failed: {exc}") from exc

    data = resp.json()

    # Extract inline image from response candidates
    try:
        candidates = data["candidates"]
        for part in candidates[0]["content"]["parts"]:
            if "inlineData" in part:
                img_b64 = part["inlineData"]["data"]
                img_bytes = base64.b64decode(img_b64)
                output_path.write_bytes(img_bytes)
                return EnhancementResult(
                    image_path=output_path, model_used=model
                )
    except (KeyError, IndexError):
        pass

    raise EnhancementError(
        "Gemini response did not contain an image in inlineData"
    )
