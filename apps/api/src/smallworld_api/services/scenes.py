"""Group hotspots and nearby features into labeled scene seeds."""

from __future__ import annotations

import math

SCENE_CLUSTER_RADIUS_METERS = 5000
MAX_SCENES_RETURNED = 12
DEDUP_DISTANCE_METERS = 2000

_SCENE_TYPE_PRIORITY = [
    "peak-water",
    "peak-ridge",
    "cliff-water",
    "multi-peak",
    "mixed-terrain",
]

_SCENE_SUMMARIES = {
    "peak-water": "Summit overlooking water feature",
    "peak-ridge": "Prominent summit with connecting skyline ridge",
    "cliff-water": "Dramatic cliff face above water channel",
    "multi-peak": "Cluster of prominent summits",
    "mixed-terrain": "Varied terrain with multiple interesting features",
}


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance in meters between two lat/lng points."""
    R = 6378137.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _feature_center(feat: dict) -> dict:
    """Get the center point of a feature (point or line)."""
    if "center" in feat:
        return feat["center"]
    path = feat.get("path", [])
    if not path:
        return {"lat": 0, "lng": 0}
    mid = path[len(path) // 2]
    return mid


def _classify_scene(feature_ids: list[str]) -> str:
    has_peak = any(fid.startswith("peak-") for fid in feature_ids)
    has_ridge = any(fid.startswith("ridge-") for fid in feature_ids)
    has_cliff = any(fid.startswith("cliff-") for fid in feature_ids)
    has_water = any(fid.startswith("water-") for fid in feature_ids)
    peak_count = sum(1 for fid in feature_ids if fid.startswith("peak-"))

    if has_peak and has_water:
        return "peak-water"
    if has_peak and has_ridge:
        return "peak-ridge"
    if has_cliff and has_water:
        return "cliff-water"
    if peak_count >= 2:
        return "multi-peak"
    return "mixed-terrain"


def group_scenes(
    hotspots: list[dict],
    all_features: dict[str, list[dict]],
    cluster_radius: float = SCENE_CLUSTER_RADIUS_METERS,
    max_scenes: int = MAX_SCENES_RETURNED,
    dedup_distance: float = DEDUP_DISTANCE_METERS,
) -> list[dict]:
    """Build scene seeds from hotspots and nearby features.

    all_features should have keys: peaks, ridges, cliffs, waterChannels
    """
    # Flatten all features with their IDs and centers
    feature_index: list[tuple[str, dict, dict]] = []  # (id, center, feature)
    for kind in ["peaks", "ridges", "cliffs", "waterChannels"]:
        for feat in all_features.get(kind, []):
            fid = feat.get("id", "")
            center = _feature_center(feat)
            feature_index.append((fid, center, feat))

    scenes: list[dict] = []

    for hotspot in hotspots:
        hc = hotspot["center"]
        nearby_ids: list[str] = []
        nearby_scores: list[float] = []

        for fid, fc, feat in feature_index:
            dist = _haversine(hc["lat"], hc["lng"], fc["lat"], fc["lng"])
            if dist <= cluster_radius:
                nearby_ids.append(fid)
                nearby_scores.append(feat.get("score", 0.5))

        # Require at least 2 anchor features
        if len(nearby_ids) < 2:
            # Allow a single strong peak + ridge
            has_strong_peak = any(
                fid.startswith("peak-") and score > 0.7
                for fid, score in zip(nearby_ids, nearby_scores)
            )
            has_ridge = any(fid.startswith("ridge-") for fid in nearby_ids)
            if not (has_strong_peak and has_ridge):
                continue

        scene_type = _classify_scene(nearby_ids)
        mean_anchor_score = sum(nearby_scores) / len(nearby_scores) if nearby_scores else 0
        scene_score = 0.6 * hotspot["score"] + 0.4 * mean_anchor_score

        scenes.append(
            {
                "center": hc,
                "featureIds": nearby_ids,
                "type": scene_type,
                "summary": _SCENE_SUMMARIES.get(scene_type, ""),
                "score": round(scene_score, 2),
                "hotspot_score": hotspot["score"],
            }
        )

    # Deduplicate: if two scenes are within dedup_distance and share >50% features, keep higher
    deduped: list[dict] = []
    for scene in sorted(scenes, key=lambda s: -s["score"]):
        is_dup = False
        for existing in deduped:
            dist = _haversine(
                scene["center"]["lat"],
                scene["center"]["lng"],
                existing["center"]["lat"],
                existing["center"]["lng"],
            )
            if dist < dedup_distance:
                overlap = set(scene["featureIds"]) & set(existing["featureIds"])
                union = set(scene["featureIds"]) | set(existing["featureIds"])
                if union and len(overlap) / len(union) > 0.5:
                    is_dup = True
                    break
        if not is_dup:
            deduped.append(scene)

    # Sort by type priority then score
    def sort_key(s: dict) -> tuple:
        type_rank = _SCENE_TYPE_PRIORITY.index(s["type"]) if s["type"] in _SCENE_TYPE_PRIORITY else 99
        return (type_rank, -s["score"])

    deduped.sort(key=sort_key)

    result = []
    for i, scene in enumerate(deduped[:max_scenes]):
        del scene["hotspot_score"]
        scene["id"] = f"scene-{i + 1}"
        result.append(scene)
    return result
