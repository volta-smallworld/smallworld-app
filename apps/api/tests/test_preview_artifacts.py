import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from smallworld_api.main import app
from smallworld_api.services.preview_artifacts import (
    artifact_url,
    cleanup_expired,
    ensure_preview_dir,
    generate_preview_id,
    get_artifact_path,
    save_artifact,
    save_manifest,
    save_request,
)

client = TestClient(app)


def test_ensure_preview_dir(tmp_path):
    d = ensure_preview_dir(str(tmp_path), "preview_abc")
    assert d.is_dir()
    assert d.name == "preview_abc"


def test_save_artifact(tmp_path):
    d = ensure_preview_dir(str(tmp_path), "preview_abc")
    p = save_artifact(d, "raw", b"\x89PNG fake")
    assert p.exists()
    assert p.read_bytes() == b"\x89PNG fake"


def test_save_manifest(tmp_path):
    d = ensure_preview_dir(str(tmp_path), "preview_abc")
    data = {"id": "preview_abc", "status": "completed"}
    p = save_manifest(d, data)
    assert p.exists()
    loaded = json.loads(p.read_text())
    assert loaded["id"] == "preview_abc"


def test_save_request(tmp_path):
    d = ensure_preview_dir(str(tmp_path), "preview_abc")
    data = {"camera": {"lat": 39.0}}
    p = save_request(d, data)
    assert p.exists()
    loaded = json.loads(p.read_text())
    assert loaded["camera"]["lat"] == 39.0


def test_get_artifact_path_exists(tmp_path):
    d = ensure_preview_dir(str(tmp_path), "preview_abc")
    (d / "raw.png").write_bytes(b"fake")
    result = get_artifact_path(str(tmp_path), "preview_abc", "raw")
    assert result is not None
    assert result.name == "raw.png"


def test_get_artifact_path_missing(tmp_path):
    result = get_artifact_path(str(tmp_path), "nonexistent", "raw")
    assert result is None


def test_artifact_url():
    assert (
        artifact_url("preview_123", "raw")
        == "/api/v1/previews/preview_123/artifacts/raw"
    )


def test_generate_preview_id():
    id1 = generate_preview_id()
    id2 = generate_preview_id()
    assert id1.startswith("preview_")
    assert id2.startswith("preview_")
    assert id1 != id2


def test_cleanup_expired(tmp_path):
    # Create two preview dirs
    old_dir = tmp_path / "preview_old"
    old_dir.mkdir()
    (old_dir / "raw.png").write_bytes(b"old")

    new_dir = tmp_path / "preview_new"
    new_dir.mkdir()
    (new_dir / "raw.png").write_bytes(b"new")

    # Make old_dir look old (48 hours ago)
    old_time = time.time() - 48 * 3600
    os.utime(old_dir, (old_time, old_time))

    removed = cleanup_expired(str(tmp_path), ttl_hours=24)
    assert removed == 1
    assert not old_dir.exists()
    assert new_dir.exists()


def test_artifact_route_serves_raw(tmp_path):
    preview_id = "preview_serve_test"
    d = ensure_preview_dir(str(tmp_path), preview_id)
    (d / "raw.png").write_bytes(b"\x89PNG fake image data")

    with patch(
        "smallworld_api.routes.previews.get_artifact_path",
        return_value=d / "raw.png",
    ):
        resp = client.get(f"/api/v1/previews/{preview_id}/artifacts/raw")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


def test_artifact_route_unknown_id():
    resp = client.get("/api/v1/previews/nonexistent/artifacts/raw")
    assert resp.status_code == 404


def test_artifact_route_unknown_variant():
    resp = client.get("/api/v1/previews/test/artifacts/unknown")
    assert resp.status_code == 404
