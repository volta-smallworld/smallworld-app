"""Headless Cesium renderer via Puppeteer."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RenderResult:
    image_path: Path
    frame_state: dict = field(default_factory=dict)


class RenderError(Exception):
    """Raised when the render subprocess fails."""


class RenderTimeoutError(Exception):
    """Raised when the render subprocess times out."""


_SCRIPT_PATH = (
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
) -> RenderResult:
    payload = {
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
    if cesium_ion_token:
        payload["cesiumIonToken"] = cesium_ion_token
    if mapbox_access_token:
        payload["mapboxAccessToken"] = mapbox_access_token
    if google_maps_api_key:
        payload["googleMapsApiKey"] = google_maps_api_key

    encoded = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).decode().rstrip("=")
    render_url = f"{base_url}?payload={encoded}"
    timeout_ms = timeout_seconds * 1000

    cmd = [
        "node",
        str(_SCRIPT_PATH),
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

    logger.info("Launching render: %s", " ".join(cmd))

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
