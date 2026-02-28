"""Style reference artifact management.

Handles upload persistence, capability checks, TTL cleanup, and
loading of pre-computed artifacts for a style reference.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from smallworld_api.config import settings

logger = logging.getLogger(__name__)

# Lazy capability flags
_clip_available: bool | None = None
_lpips_available: bool | None = None


def _check_clip() -> bool:
    global _clip_available
    if _clip_available is not None:
        return _clip_available
    try:
        import open_clip  # noqa: F401
        _clip_available = True
    except ImportError:
        logger.warning("open_clip not available")
        _clip_available = False
    return _clip_available


def _check_lpips() -> bool:
    global _lpips_available
    if _lpips_available is not None:
        return _lpips_available
    try:
        import lpips  # noqa: F401
        _lpips_available = True
    except ImportError:
        logger.warning("lpips not available")
        _lpips_available = False
    return _lpips_available


def _check_hed() -> bool:
    from smallworld_api.services.style_fingerprint import is_hed_available
    return is_hed_available()


def check_style_capabilities() -> dict:
    """Return style capabilities status dict.

    All three models (HED, CLIP, LPIPS) must be available for full
    style functionality. If any is missing, ``enabled`` is ``False``.
    """
    hed_ok = _check_hed()
    clip_ok = _check_clip()
    lpips_ok = _check_lpips()

    # For the capabilities endpoint, we consider the system enabled if
    # at least HED (or Canny fallback) is available. The fingerprint
    # service falls back to Canny if HED weights are missing, so we
    # treat fingerprinting as always available.
    # Full style requires all three for verification, but search works
    # with fingerprint alone.
    enabled = True  # fingerprint always available via Canny fallback

    messages: list[str] = []
    if not hed_ok:
        messages.append("HED weights not loaded (using Canny fallback)")
    if not clip_ok:
        messages.append("CLIP model not available")
    if not lpips_ok:
        messages.append("LPIPS model not available")

    message = "; ".join(messages) if messages else None

    return {
        "enabled": enabled,
        "hedLoaded": hed_ok,
        "clipLoaded": clip_ok,
        "lpipsLoaded": lpips_ok,
        "maxUploadBytes": settings.style_upload_max_bytes,
        "message": message,
    }


def _artifacts_dir() -> Path:
    return Path(settings.style_artifacts_dir)


def _reference_dir(reference_id: str) -> Path:
    return _artifacts_dir() / reference_id


def _generate_reference_id() -> str:
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    short_id = uuid.uuid4().hex[:8]
    return f"style-ref-{date_str}-{short_id}"


def save_reference_artifacts(
    image_data: bytes,
    normalized: np.ndarray,
    fingerprint_result: dict,
    filename: str,
    content_type: str,
    label: str | None,
) -> str:
    """Persist reference artifacts to disk. Returns the reference ID."""
    reference_id = _generate_reference_id()
    ref_dir = _reference_dir(reference_id)
    ref_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save original
    ext = _ext_from_content_type(content_type)
    original_path = ref_dir / f"original{ext}"
    original_path.write_bytes(image_data)

    # 2. Save normalised PNG
    norm_img = Image.fromarray(normalized)
    norm_path = ref_dir / "normalized.png"
    norm_img.save(norm_path, format="PNG")

    # 3. Save HED edge map
    edge_map = fingerprint_result["edge_map"]
    edge_uint8 = (np.clip(edge_map, 0, 1) * 255).astype(np.uint8)
    edge_img = Image.fromarray(edge_uint8, mode="L")
    edge_path = ref_dir / "hed_edges.png"
    edge_img.save(edge_path, format="PNG")

    # 4. Save fingerprint vector
    vector = fingerprint_result["vector"]
    np.save(str(ref_dir / "fingerprint_vector.npy"), vector)

    # 5. Save fingerprint JSON
    summary = fingerprint_result["summary"]
    fp_json = ref_dir / "fingerprint.json"
    fp_json.write_text(json.dumps(summary, indent=2))

    # 6. Save metadata
    metadata = {
        "referenceId": reference_id,
        "filename": filename,
        "contentType": content_type,
        "label": label,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "normalizedShape": list(normalized.shape[:2]),
    }
    meta_path = ref_dir / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2))

    logger.info("Saved style reference artifacts: %s", reference_id)
    return reference_id


def load_reference_artifacts(reference_id: str) -> dict | None:
    """Load pre-computed artifacts for a reference ID.

    Returns a dict with keys: fingerprint (vector), summary, edge_map,
    normalized, metadata. Returns None if not found or expired.
    """
    ref_dir = _reference_dir(reference_id)
    if not ref_dir.exists():
        return None

    # Check TTL
    meta_path = ref_dir / "metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        created_at = meta.get("createdAt")
        if created_at:
            created = datetime.fromisoformat(created_at)
            age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
            if age_hours > settings.style_reference_ttl_hours:
                logger.info("Reference %s expired (%.1fh old)", reference_id, age_hours)
                shutil.rmtree(ref_dir, ignore_errors=True)
                return None
    else:
        return None

    try:
        vector = np.load(str(ref_dir / "fingerprint_vector.npy"))
        summary = json.loads((ref_dir / "fingerprint.json").read_text())

        edge_path = ref_dir / "hed_edges.png"
        edge_map = None
        if edge_path.exists():
            edge_img = Image.open(edge_path).convert("L")
            edge_map = np.array(edge_img).astype(np.float32) / 255.0

        norm_path = ref_dir / "normalized.png"
        normalized = None
        if norm_path.exists():
            normalized = np.array(Image.open(norm_path).convert("RGB"))

        metadata = json.loads(meta_path.read_text())

        return {
            "fingerprint": vector,
            "summary": summary,
            "edge_map": edge_map,
            "normalized": normalized,
            "metadata": metadata,
        }
    except Exception:
        logger.exception("Failed to load artifacts for %s", reference_id)
        return None


def cleanup_expired_references() -> int:
    """Remove expired reference directories. Returns count of removed."""
    base = _artifacts_dir()
    if not base.exists():
        return 0

    removed = 0
    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "metadata.json"
        if not meta_path.exists():
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
            continue
        try:
            meta = json.loads(meta_path.read_text())
            created_at = meta.get("createdAt")
            if created_at:
                created = datetime.fromisoformat(created_at)
                age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
                if age_hours > settings.style_reference_ttl_hours:
                    shutil.rmtree(entry, ignore_errors=True)
                    removed += 1
        except Exception:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1

    if removed:
        logger.info("Cleaned up %d expired style references", removed)
    return removed


def _ext_from_content_type(ct: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    return mapping.get(ct, ".bin")
