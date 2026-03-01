"""Gemini image-editing enhancement for preview renders."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

SYSTEM_ENHANCEMENT_PROMPT = (
    "Photorealistic enhancement of this exact terrain. If any area of the image "
    "shows a flat, solid-colored background (black, gray, etc.) where sky should be, "
    "replace ONLY that area with a natural sky with soft clouds. Do NOT add, modify, "
    "or extend any landforms, mountains, hills, trees, buildings, or terrain features. "
    "The landscape composition, topography, and all ground-level details must remain "
    "identical to the source image. Only improve texture resolution, lighting realism, "
    "and color grading of existing elements. The horizon line and all terrain "
    "silhouettes must stay exactly as shown — do not generate additional geography "
    "or extend the landscape."
)

DEFAULT_CREATIVE_PROMPT = (
    "Ultra-realistic landscape photograph, golden hour lighting, "
    "85mm lens, high dynamic range, cinematic color grading."
)
# Backwards-compatible alias
DEFAULT_ENHANCEMENT_PROMPT = DEFAULT_CREATIVE_PROMPT
DEFAULT_GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image-preview"
LEGACY_GEMINI_IMAGE_MODELS = {
    "gemini-2.0-flash-exp-image-generation": DEFAULT_GEMINI_IMAGE_MODEL,
    "gemini-2.0-flash-preview-image-generation": DEFAULT_GEMINI_IMAGE_MODEL,
}


@dataclass
class EnhancementResult:
    image_path: Path
    model_used: str


class EnhancementError(Exception):
    """Raised when enhancement fails."""


class EnhancementNotConfiguredError(Exception):
    """Raised when enhancement is not configured."""


def build_enhancement_prompt(dynamic_prompt: str | None = None) -> str:
    """Combine system guardrails with the caller's creative prompt.

    The system prompt protects terrain fidelity; the dynamic prompt
    controls creative direction (lighting, atmosphere, season, mood).
    When no dynamic prompt is supplied, the default creative prompt is used.
    """
    creative = dynamic_prompt if dynamic_prompt else DEFAULT_CREATIVE_PROMPT
    return SYSTEM_ENHANCEMENT_PROMPT + "\n\n---\n\n" + creative


def _resolve_model_name(model: str) -> str:
    normalized = model.strip()
    if not normalized:
        return normalized
    return LEGACY_GEMINI_IMAGE_MODELS.get(normalized, normalized)


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

    resolved_model = _resolve_model_name(model)
    raw_bytes = raw_image_path.read_bytes()
    b64_image = base64.b64encode(raw_bytes).decode()

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{resolved_model}:generateContent?key={api_key}"
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
        ]
    }

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        try:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            try:
                payload = exc.response.json()
                detail = payload.get("error", {}).get("message", detail)
            except ValueError:
                pass
            raise EnhancementError(
                f"Gemini API returned {exc.response.status_code}: {detail}"
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
                    image_path=output_path, model_used=resolved_model
                )
    except (KeyError, IndexError):
        pass

    response_text = " ".join(
        part.get("text", "")
        for candidate in data.get("candidates", [])
        for part in candidate.get("content", {}).get("parts", [])
        if isinstance(part, dict)
    ).strip()
    if response_text:
        logger.warning(
            "Gemini returned text-only enhancement response: %s",
            response_text,
        )

    raise EnhancementError(
        "Gemini response did not contain an image in inlineData"
    )
