"""Geometry-based composition verification.

Projects 3-D anchor points into normalised screen coordinates using the
camera pose, then compares them against desired composition target positions.
"""

from __future__ import annotations

import logging
import math

from smallworld_api.models.previews import (
    CompositionAnchor,
    CompositionTemplate,
    CompositionVerification,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

# WGS-84 constants
WGS84_A = 6378137.0  # semi-major axis (m)
WGS84_E2 = 0.00669437999014  # first eccentricity squared

# Threshold in pixels — anchor must land within this distance of the
# desired position for the composition to "pass".
_PASS_THRESHOLD_PX = 80.0


# ── Coordinate helpers ────────────────────────────────────────────────────


def _geodetic_to_ecef(
    lat_deg: float, lng_deg: float, alt_m: float
) -> tuple[float, float, float]:
    lat = math.radians(lat_deg)
    lng = math.radians(lng_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lng = math.sin(lng)
    cos_lng = math.cos(lng)

    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    x = (n + alt_m) * cos_lat * cos_lng
    y = (n + alt_m) * cos_lat * sin_lng
    z = (n * (1.0 - WGS84_E2) + alt_m) * sin_lat
    return x, y, z


def _ecef_to_enu(
    x: float,
    y: float,
    z: float,
    ref_lat_deg: float,
    ref_lng_deg: float,
    ref_alt_m: float,
) -> tuple[float, float, float]:
    rx, ry, rz = _geodetic_to_ecef(ref_lat_deg, ref_lng_deg, ref_alt_m)
    dx, dy, dz = x - rx, y - ry, z - rz

    lat = math.radians(ref_lat_deg)
    lng = math.radians(ref_lng_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lng = math.sin(lng)
    cos_lng = math.cos(lng)

    e = -sin_lng * dx + cos_lng * dy
    n = -sin_lat * cos_lng * dx - sin_lat * sin_lng * dy + cos_lat * dz
    u = cos_lat * cos_lng * dx + cos_lat * sin_lng * dy + sin_lat * dz
    return e, n, u


def _project_to_screen(
    enu: tuple[float, float, float],
    heading_deg: float,
    pitch_deg: float,
    roll_deg: float,
    fov_deg: float,
    width: int,
    height: int,
) -> tuple[float, float] | None:
    """Project an ENU point to pixel coordinates.

    Returns ``None`` if the point is behind the camera.
    """
    e, n, u = enu
    h = math.radians(heading_deg)
    p = math.radians(pitch_deg)
    r = math.radians(roll_deg)

    # Rotate from ENU into camera-forward frame.
    # Camera forward = heading rotated north, pitched up, rolled.
    # Step 1: rotate around Up by -heading (heading 0 = north = +N axis)
    cos_h, sin_h = math.cos(h), math.sin(h)
    x1 = cos_h * e + sin_h * n
    y1 = -sin_h * e + cos_h * n
    z1 = u

    # Step 2: rotate around Right by -pitch (negative pitch = looking down)
    cos_p, sin_p = math.cos(p), math.sin(p)
    x2 = x1
    y2 = cos_p * y1 - sin_p * z1
    z2 = sin_p * y1 + cos_p * z1

    # Step 3: rotate around Forward by -roll
    cos_r, sin_r = math.cos(r), math.sin(r)
    x3 = cos_r * x2 + sin_r * z2
    y3 = y2
    z3 = -sin_r * x2 + cos_r * z2

    # In camera space: y3 = forward, x3 = right, z3 = up
    forward = y3
    if forward <= 0:
        return None  # behind camera

    half_fov = math.radians(fov_deg / 2.0)
    aspect = width / height

    # Perspective divide
    ndc_x = x3 / (forward * math.tan(half_fov) * aspect)
    ndc_y = -z3 / (forward * math.tan(half_fov))

    # NDC → pixel
    px = (ndc_x + 1.0) * 0.5 * width
    py = (ndc_y + 1.0) * 0.5 * height
    return px, py


# ── Public API ────────────────────────────────────────────────────────────


def verify_composition(
    *,
    camera_lat: float,
    camera_lng: float,
    camera_alt_meters: float,
    heading_deg: float,
    pitch_deg: float,
    roll_deg: float,
    fov_deg: float,
    viewport_width: int,
    viewport_height: int,
    template: CompositionTemplate,
    anchors: list[CompositionAnchor] | None,
    horizon_ratio: float | None,
) -> CompositionVerification:
    # No anchors → skip
    if not anchors:
        return CompositionVerification(
            status=VerificationStatus.SKIPPED,
            template=template.value,
            notes="No anchors supplied; verification skipped.",
        )

    # Unsupported template
    if template == CompositionTemplate.LEADING_LINE:
        return CompositionVerification(
            status=VerificationStatus.UNSUPPORTED_TEMPLATE,
            template=template.value,
            notes="Leading-line verification is not yet supported.",
        )

    try:
        errors_px: list[float] = []
        for anchor in anchors:
            ax, ay, az = _geodetic_to_ecef(anchor.lat, anchor.lng, anchor.altMeters)
            enu = _ecef_to_enu(
                ax, ay, az, camera_lat, camera_lng, camera_alt_meters
            )
            projected = _project_to_screen(
                enu,
                heading_deg,
                pitch_deg,
                roll_deg,
                fov_deg,
                viewport_width,
                viewport_height,
            )
            if projected is None:
                errors_px.append(
                    math.hypot(viewport_width, viewport_height)
                )  # worst-case penalty
                continue

            desired_px = anchor.desiredNormalizedX * viewport_width
            desired_py = anchor.desiredNormalizedY * viewport_height
            err = math.hypot(projected[0] - desired_px, projected[1] - desired_py)
            errors_px.append(err)

        mean_error = sum(errors_px) / len(errors_px) if errors_px else 0.0

        # Horizon error (optional)
        horizon_error: float | None = None
        if horizon_ratio is not None:
            # Approximate horizon pixel row from pitch: pitch=0 → horizon at
            # vertical centre; negative pitch moves horizon up.
            half_fov_v = math.radians(fov_deg / 2.0)
            pitch_rad = math.radians(pitch_deg)
            horizon_ndc_y = pitch_rad / half_fov_v  # [-1, 1]
            horizon_px_y = (horizon_ndc_y + 1.0) * 0.5 * viewport_height
            desired_horizon_px_y = horizon_ratio * viewport_height
            horizon_error = abs(horizon_px_y - desired_horizon_px_y)

        passes = mean_error <= _PASS_THRESHOLD_PX
        status = VerificationStatus.VERIFIED if passes else VerificationStatus.FAILED

        notes_parts: list[str] = []
        if passes:
            notes_parts.append("Anchors fall within tolerance.")
        else:
            notes_parts.append(
                f"Mean anchor error {mean_error:.1f}px exceeds {_PASS_THRESHOLD_PX}px threshold."
            )

        return CompositionVerification(
            status=status,
            template=template.value,
            passesThreshold=passes,
            meanAnchorErrorPx=round(mean_error, 1),
            horizonErrorPx=round(horizon_error, 1) if horizon_error is not None else None,
            notes=" ".join(notes_parts),
        )

    except Exception:
        logger.exception("Composition verification projection failed")
        return CompositionVerification(
            status=VerificationStatus.FAILED,
            template=template.value,
            notes="Projection math failed during verification.",
        )
