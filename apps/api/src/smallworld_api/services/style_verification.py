"""Render verification for style references.

Compares a rendered preview image against the uploaded reference using
CLIP cosine similarity, LPIPS perceptual distance, and HED edge
fingerprint similarity.
"""

from __future__ import annotations

import logging
from io import BytesIO

import numpy as np
from PIL import Image

from smallworld_api.config import settings
from smallworld_api.services.style_fingerprint import (
    extract_fingerprint,
    cosine_similarity,
)

logger = logging.getLogger(__name__)

# Lazy-loaded models
_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None
_lpips_model = None
_torch = None


def _ensure_torch():
    global _torch
    if _torch is None:
        import torch
        _torch = torch
    return _torch


def _load_clip():
    global _clip_model, _clip_preprocess
    if _clip_model is not None:
        return True
    try:
        import open_clip
        torch = _ensure_torch()

        model, _, preprocess = open_clip.create_model_and_transforms(
            settings.style_clip_model_name,
            pretrained=settings.style_clip_pretrained,
        )
        model.eval()
        _clip_model = model
        _clip_preprocess = preprocess
        logger.info("CLIP model loaded: %s", settings.style_clip_model_name)
        return True
    except Exception:
        logger.exception("Failed to load CLIP model")
        return False


def _load_lpips():
    global _lpips_model
    if _lpips_model is not None:
        return True
    try:
        import lpips
        _ensure_torch()

        _lpips_model = lpips.LPIPS(net=settings.style_lpips_backbone)
        _lpips_model.eval()
        logger.info("LPIPS model loaded: %s", settings.style_lpips_backbone)
        return True
    except Exception:
        logger.exception("Failed to load LPIPS model")
        return False


def _compute_clip_similarity(
    ref_image: np.ndarray, preview_image: np.ndarray
) -> float | None:
    """Compute CLIP cosine similarity between two images."""
    if not _load_clip() or _clip_model is None or _clip_preprocess is None:
        return None

    try:
        torch = _ensure_torch()

        ref_pil = Image.fromarray(ref_image)
        preview_pil = Image.fromarray(preview_image)

        ref_tensor = _clip_preprocess(ref_pil).unsqueeze(0)
        preview_tensor = _clip_preprocess(preview_pil).unsqueeze(0)

        with torch.no_grad():
            ref_features = _clip_model.encode_image(ref_tensor)
            preview_features = _clip_model.encode_image(preview_tensor)

            ref_features = ref_features / ref_features.norm(dim=-1, keepdim=True)
            preview_features = preview_features / preview_features.norm(dim=-1, keepdim=True)

            similarity = (ref_features @ preview_features.T).item()

        return float(np.clip(similarity, 0, 1))
    except Exception:
        logger.exception("CLIP similarity computation failed")
        return None


def _compute_lpips_distance(
    ref_image: np.ndarray, preview_image: np.ndarray
) -> float | None:
    """Compute LPIPS perceptual distance between two images."""
    if not _load_lpips() or _lpips_model is None:
        return None

    try:
        torch = _ensure_torch()

        # Resize both to 256x256 for LPIPS
        ref_pil = Image.fromarray(ref_image).resize((256, 256), Image.LANCZOS)
        preview_pil = Image.fromarray(preview_image).resize((256, 256), Image.LANCZOS)

        # Convert to tensors: [B, C, H, W] in [-1, 1]
        ref_np = np.array(ref_pil).astype(np.float32) / 127.5 - 1.0
        preview_np = np.array(preview_pil).astype(np.float32) / 127.5 - 1.0

        ref_tensor = torch.from_numpy(ref_np).permute(2, 0, 1).unsqueeze(0)
        preview_tensor = torch.from_numpy(preview_np).permute(2, 0, 1).unsqueeze(0)

        with torch.no_grad():
            distance = _lpips_model(ref_tensor, preview_tensor).item()

        # Clamp to [0, 1]
        return float(np.clip(distance, 0, 1))
    except Exception:
        logger.exception("LPIPS distance computation failed")
        return None


def _compute_edge_similarity(
    ref_image: np.ndarray, preview_image: np.ndarray
) -> float | None:
    """Compute edge fingerprint similarity between two images."""
    try:
        ref_fp = extract_fingerprint(ref_image)
        preview_fp = extract_fingerprint(preview_image)

        similarity = cosine_similarity(ref_fp["vector"], preview_fp["vector"])
        return float(np.clip(similarity, 0, 1))
    except Exception:
        logger.exception("Edge similarity computation failed")
        return None


def verify_rendered_preview(
    reference_artifacts: dict,
    preview_data: bytes,
    pre_render_score: float,
) -> dict:
    """Verify a rendered preview against reference artifacts.

    Parameters
    ----------
    reference_artifacts : dict
        Loaded reference artifacts (from load_reference_artifacts).
    preview_data : bytes
        Raw bytes of the rendered preview image.
    pre_render_score : float
        The pre-render style score for this candidate.

    Returns
    -------
    dict
        With keys: verificationStatus, clipSimilarity, lpipsDistance,
        edgeSimilarity, finalStyleScore, warnings.
    """
    warnings: list[str] = []

    # Decode preview
    try:
        preview_img = Image.open(BytesIO(preview_data)).convert("RGB")
        preview_rgb = np.array(preview_img)
    except Exception:
        return {
            "verificationStatus": "failed",
            "clipSimilarity": None,
            "lpipsDistance": None,
            "edgeSimilarity": None,
            "finalStyleScore": None,
            "warnings": ["Failed to decode preview image"],
        }

    ref_rgb = reference_artifacts.get("normalized")
    if ref_rgb is None:
        return {
            "verificationStatus": "failed",
            "clipSimilarity": None,
            "lpipsDistance": None,
            "edgeSimilarity": None,
            "finalStyleScore": None,
            "warnings": ["Reference normalized image not available"],
        }

    # Compute metrics
    clip_sim = _compute_clip_similarity(ref_rgb, preview_rgb)
    lpips_dist = _compute_lpips_distance(ref_rgb, preview_rgb)
    edge_sim = _compute_edge_similarity(ref_rgb, preview_rgb)

    # Track successes
    successful_metrics: dict[str, float] = {}
    if clip_sim is not None:
        successful_metrics["clip"] = clip_sim
    else:
        warnings.append("CLIP similarity computation failed")

    if lpips_dist is not None:
        successful_metrics["lpips"] = lpips_dist
    else:
        warnings.append("LPIPS distance computation failed")

    if edge_sim is not None:
        successful_metrics["edge"] = edge_sim
    else:
        warnings.append("Edge similarity computation failed")

    # Determine status
    if len(successful_metrics) == 3:
        status = "verified"
    elif len(successful_metrics) > 0:
        status = "partial"
    else:
        return {
            "verificationStatus": "failed",
            "clipSimilarity": None,
            "lpipsDistance": None,
            "edgeSimilarity": None,
            "finalStyleScore": None,
            "warnings": warnings,
        }

    # Compute render verification score
    # Standard weights: clip=0.50, edge=0.30, lpips=0.20
    render_weights = {}
    if "clip" in successful_metrics:
        render_weights["clip"] = 0.50
    if "edge" in successful_metrics:
        render_weights["edge"] = 0.30
    if "lpips" in successful_metrics:
        render_weights["lpips"] = 0.20

    # Renormalize weights if partial
    weight_sum = sum(render_weights.values())
    if weight_sum > 0:
        for k in render_weights:
            render_weights[k] /= weight_sum

    render_score = 0.0
    if "clip" in render_weights:
        render_score += render_weights["clip"] * clip_sim
    if "edge" in render_weights:
        render_score += render_weights["edge"] * edge_sim
    if "lpips" in render_weights:
        render_score += render_weights["lpips"] * (1.0 - lpips_dist)

    # Final style score
    final_style_score = 0.60 * pre_render_score + 0.40 * render_score

    return {
        "verificationStatus": status,
        "clipSimilarity": round(clip_sim, 4) if clip_sim is not None else None,
        "lpipsDistance": round(lpips_dist, 4) if lpips_dist is not None else None,
        "edgeSimilarity": round(edge_sim, 4) if edge_sim is not None else None,
        "finalStyleScore": round(final_style_score, 4),
        "warnings": warnings,
    }
