"""Local artifact storage for preview renders."""

from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_preview_id() -> str:
    return f"preview_{uuid.uuid4().hex}"


def ensure_preview_dir(artifacts_root: str, preview_id: str) -> Path:
    d = Path(artifacts_root) / preview_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_artifact(preview_dir: Path, variant: str, data: bytes) -> Path:
    p = preview_dir / f"{variant}.png"
    p.write_bytes(data)
    return p


def save_manifest(preview_dir: Path, manifest: dict) -> Path:
    p = preview_dir / "manifest.json"
    p.write_text(json.dumps(manifest, default=str, indent=2))
    return p


def save_request(preview_dir: Path, request_data: dict) -> Path:
    p = preview_dir / "request.json"
    p.write_text(json.dumps(request_data, default=str, indent=2))
    return p


def get_artifact_path(
    artifacts_root: str, preview_id: str, variant: str
) -> Path | None:
    p = Path(artifacts_root) / preview_id / f"{variant}.png"
    return p if p.is_file() else None


def artifact_url(preview_id: str, variant: str) -> str:
    return f"/api/v1/previews/{preview_id}/artifacts/{variant}"


def cleanup_expired(artifacts_root: str, ttl_hours: int) -> int:
    root = Path(artifacts_root)
    if not root.is_dir():
        return 0

    cutoff = time.time() - ttl_hours * 3600
    removed = 0
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            if child.stat().st_mtime < cutoff:
                shutil.rmtree(child)
                removed += 1
        except Exception:
            logger.warning("Failed to clean up %s", child, exc_info=True)
    return removed
