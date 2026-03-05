"""Headless Cesium renderer via Puppeteer."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# Default preview resolution — 1920x1080 for high-fidelity output.
DEFAULT_RENDER_WIDTH = 1920
DEFAULT_RENDER_HEIGHT = 1080

# Provider type used throughout the render pipeline.
ProviderName = Literal["google_3d", "ion", "osm"]


@dataclass
class RenderResult:
    image_path: Path
    frame_state: dict = field(default_factory=dict)


class RenderError(Exception):
    """Raised when the render subprocess fails."""


class RenderTimeoutError(Exception):
    """Raised when the render subprocess times out."""


def _resolve_script_path() -> Path:
    from smallworld_api.config import settings

    if settings.render_script_path:
        return Path(settings.render_script_path)
    return (
        Path(__file__).resolve().parent.parent.parent.parent.parent.parent
        / "apps"
        / "web"
        / "scripts"
        / "render-preview.mjs"
    )


async def render_preview(
    *,
    base_url: str,
    camera_lat: float,
    camera_lng: float,
    camera_alt: float,
    heading_deg: float,
    pitch_deg: float,
    roll_deg: float,
    fov_deg: float,
    viewport_width: int,
    viewport_height: int,
    output_path: Path,
    timeout_seconds: int,
    cesium_ion_token: str = "",
    mapbox_access_token: str = "",
    google_maps_api_key: str = "",
    agl_floor_meters: float | None = None,
    terrain_clamp_enabled: bool | None = None,
    terrain_sample_timeout_ms: int | None = None,
    provider: ProviderName | None = None,
) -> RenderResult:
    """Render a preview screenshot via the headless Cesium renderer.

    Parameters
    ----------
    provider
        Explicit tile-source provider to use for this render.

        * ``"google_3d"`` — Google Photorealistic 3D Tiles (requires
          *google_maps_api_key*).
        * ``"ion"``       — Cesium Ion world terrain + imagery (requires
          *cesium_ion_token*).
        * ``"osm"``       — OpenStreetMap imagery on an ellipsoid.  No
          external keys needed.
        * ``None``        — Legacy behaviour: pass whatever keys are
          provided and let the frontend decide.
    """
    payload: dict = {
        "camera": {
            "lat": camera_lat,
            "lng": camera_lng,
            "altMeters": camera_alt,
            "headingDeg": heading_deg,
            "pitchDeg": pitch_deg,
            "rollDeg": roll_deg,
            "fovDeg": fov_deg,
        },
        "viewport": {"width": viewport_width, "height": viewport_height},
    }

    # ── Provider-aware key injection ──────────────────────────────────────
    # When an explicit *provider* is given we only include the keys that
    # the provider needs and set the ``provider`` hint so the frontend
    # component can take the fast path.
    if provider == "google_3d":
        if google_maps_api_key:
            payload["googleMapsApiKey"] = google_maps_api_key
        payload["provider"] = "google_3d"
    elif provider == "ion":
        if cesium_ion_token:
            payload["cesiumIonToken"] = cesium_ion_token
        if mapbox_access_token:
            payload["mapboxAccessToken"] = mapbox_access_token
        payload["provider"] = "ion"
    elif provider == "osm":
        payload["provider"] = "osm"
    else:
        # Legacy behaviour — forward all available keys
        if cesium_ion_token:
            payload["cesiumIonToken"] = cesium_ion_token
        if mapbox_access_token:
            payload["mapboxAccessToken"] = mapbox_access_token
        if google_maps_api_key:
            payload["googleMapsApiKey"] = google_maps_api_key

    # Renderer-side terrain clamp safety block
    if terrain_clamp_enabled is not None or agl_floor_meters is not None:
        payload["safety"] = {
            "aglFloorMeters": agl_floor_meters if agl_floor_meters is not None else 5.0,
            "enabled": terrain_clamp_enabled if terrain_clamp_enabled is not None else True,
            "sampleTimeoutMs": terrain_sample_timeout_ms if terrain_sample_timeout_ms is not None else 3000,
        }

    encoded = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).decode().rstrip("=")
    render_url = f"{base_url}?payload={encoded}"
    timeout_ms = timeout_seconds * 1000

    cmd = [
        "node",
        str(_resolve_script_path()),
        "--url",
        render_url,
        "--output",
        str(output_path),
        "--width",
        str(viewport_width),
        "--height",
        str(viewport_height),
        "--timeout",
        str(timeout_ms),
    ]

    logger.info("Launching render (provider=%s): %s", provider or "auto", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_seconds + 5
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RenderTimeoutError(
            f"Render timed out after {timeout_seconds}s"
        )

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace").strip()
        raise RenderError(
            f"Render exited with code {proc.returncode}: {err_msg}"
        )

    # Parse frame state from stdout
    frame_state: dict = {}
    stdout_text = stdout.decode(errors="replace").strip()
    if stdout_text:
        try:
            frame_state = json.loads(stdout_text)
        except json.JSONDecodeError:
            logger.warning("Could not parse frame state from renderer stdout")

    return RenderResult(image_path=output_path, frame_state=frame_state)
