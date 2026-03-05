"""Gemini vision critique for preview renders.

Evaluates a raw render image and suggests camera pose adjustments
to improve composition, exposure, terrain visibility, and aesthetics.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

CRITIQUE_PROMPT_TEMPLATE = """\
You are a professional landscape photography critic evaluating a 3D terrain render.

Composition context:
- Template: {template}
- Subject: {subject_label}
- Desired horizon ratio: {horizon_ratio}

Score this image on four dimensions (0-100 each):
1. **composition_score**: How well does the framing follow the {template} template?
2. **exposure_score**: Is the lighting balanced? Are details visible in shadows and highlights?
3. **terrain_visibility_score**: Is the terrain clearly visible? Are there missing tiles, flat black areas, or occluded subjects?
4. **aesthetic_score**: Overall visual appeal — interesting angles, depth, atmosphere.

Then provide an **overall_score** (0-100) as a weighted average.

If the overall score is below {threshold}, suggest camera adjustments:
- heading_delta: degrees to rotate horizontally (positive = clockwise, max ±15)
- pitch_delta: degrees to adjust vertical angle (positive = look up, max ±10)
- alt_delta: meters to adjust camera altitude (positive = higher, max ±200)
- fov_delta: degrees to adjust field of view (positive = wider, max ±5)

If the image is acceptable, set all deltas to 0.

Provide brief reasoning for your scores and adjustments.
"""

CRITIQUE_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "overall_score": {"type": "NUMBER"},
        "composition_score": {"type": "NUMBER"},
        "exposure_score": {"type": "NUMBER"},
        "terrain_visibility_score": {"type": "NUMBER"},
        "aesthetic_score": {"type": "NUMBER"},
        "reasoning": {"type": "STRING"},
        "heading_delta": {"type": "NUMBER"},
        "pitch_delta": {"type": "NUMBER"},
        "alt_delta": {"type": "NUMBER"},
        "fov_delta": {"type": "NUMBER"},
    },
    "required": [
        "overall_score",
        "composition_score",
        "exposure_score",
        "terrain_visibility_score",
        "aesthetic_score",
        "reasoning",
        "heading_delta",
        "pitch_delta",
        "alt_delta",
        "fov_delta",
    ],
}

# Delta clamp bounds
MAX_HEADING_DELTA = 15.0
MAX_PITCH_DELTA = 10.0
MAX_ALT_DELTA = 200.0
MAX_FOV_DELTA = 5.0


class CritiqueError(Exception):
    """Raised when the critique API call fails."""


class CritiqueNotConfiguredError(Exception):
    """Raised when the Gemini API key is not set."""


@dataclass
class CritiqueResult:
    iteration: int
    model_used: str
    overall_score: float
    composition_score: float
    exposure_score: float
    terrain_visibility_score: float
    aesthetic_score: float
    reasoning: str
    pose_adjustment: dict  # heading_delta, pitch_delta, alt_delta, fov_delta
    accepted: bool
    duration_ms: int


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def _select_model(iteration: int, fast_model: str, smart_model: str) -> str:
    """Iterations 1-2 use fast model, iteration 3 escalates to smart model."""
    if iteration >= 3:
        return smart_model
    return fast_model


async def critique_render(
    *,
    raw_image_path: Path,
    iteration: int,
    api_key: str,
    fast_model: str,
    smart_model: str,
    threshold: float,
    template: str = "rule_of_thirds",
    subject_label: str | None = None,
    horizon_ratio: float | None = None,
    timeout_seconds: int = 30,
) -> CritiqueResult:
    """Score a render image and suggest pose adjustments.

    Raises
    ------
    CritiqueNotConfiguredError
        When the API key is empty.
    CritiqueError
        When the Gemini API call fails.
    """
    if not api_key:
        raise CritiqueNotConfiguredError("GEMINI_API_KEY is not set")

    start = time.monotonic()
    model = _select_model(iteration, fast_model, smart_model)

    raw_bytes = raw_image_path.read_bytes()
    b64_image = base64.b64encode(raw_bytes).decode()

    prompt = CRITIQUE_PROMPT_TEMPLATE.format(
        template=template,
        subject_label=subject_label or "terrain",
        horizon_ratio=horizon_ratio if horizon_ratio is not None else "auto",
        threshold=threshold,
    )

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
            "responseMimeType": "application/json",
            "responseSchema": CRITIQUE_RESPONSE_SCHEMA,
        },
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
            raise CritiqueError(
                f"Gemini critique API returned {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise CritiqueError(
                f"Gemini critique API request failed: {exc}"
            ) from exc

    data = resp.json()

    try:
        candidates = data["candidates"]
        text = candidates[0]["content"]["parts"][0]["text"]
        scores = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise CritiqueError(
            f"Failed to parse critique response: {exc}"
        ) from exc

    overall = float(scores.get("overall_score", 0))
    composition = float(scores.get("composition_score", 0))
    exposure = float(scores.get("exposure_score", 0))
    terrain_vis = float(scores.get("terrain_visibility_score", 0))
    aesthetic = float(scores.get("aesthetic_score", 0))
    reasoning = str(scores.get("reasoning", ""))

    pose_adjustment = {
        "heading_delta": _clamp(float(scores.get("heading_delta", 0)), MAX_HEADING_DELTA),
        "pitch_delta": _clamp(float(scores.get("pitch_delta", 0)), MAX_PITCH_DELTA),
        "alt_delta": _clamp(float(scores.get("alt_delta", 0)), MAX_ALT_DELTA),
        "fov_delta": _clamp(float(scores.get("fov_delta", 0)), MAX_FOV_DELTA),
    }

    duration_ms = int((time.monotonic() - start) * 1000)

    return CritiqueResult(
        iteration=iteration,
        model_used=model,
        overall_score=overall,
        composition_score=composition,
        exposure_score=exposure,
        terrain_visibility_score=terrain_vis,
        aesthetic_score=aesthetic,
        reasoning=reasoning,
        pose_adjustment=pose_adjustment,
        accepted=overall >= threshold,
        duration_ms=duration_ms,
    )
