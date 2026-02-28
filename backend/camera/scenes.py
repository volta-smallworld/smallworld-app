"""
Scene grouping: cluster terrain features into photographable compositions.
A "scene" is a group of features that could appear together in one frame.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple
from terrain.features import Feature, FeatureSet
from log import get_logger

log = get_logger("camera.scenes")


@dataclass
class Scene:
    """A group of terrain features that form a photographable composition."""
    features: List[Feature]
    center_row: int
    center_col: int
    center_elevation: float
    scene_type: str  # e.g., "peak_lake", "double_peak", "cliff_valley"
    span_pixels: float  # approximate diagonal extent in pixels
    anchor_positions_3d: List[Tuple[float, float, float]] = field(default_factory=list)


def group_scenes(
    dem: np.ndarray,
    feature_set: FeatureSet,
    res_m: float,
    max_scene_span_m: float = 5000,
) -> List[Scene]:
    """Group nearby features into photographable scenes.

    Rules:
    - Features within max_scene_span_m of each other
    - 2-5 features per scene
    - Features at different heights provide depth
    """
    all_features = _collect_all_features(feature_set, dem)

    log.info(f"Grouping {len(all_features)} features into scenes "
             f"(max_span={max_scene_span_m}m)")

    if not all_features:
        log.info("No features to group")
        return []

    max_span_px = max_scene_span_m / res_m
    scenes = []

    # Strategy 1: Each significant peak + nearby features
    for peak in feature_set.peaks[:15]:
        nearby = _find_nearby(peak, all_features, max_span_px)
        if len(nearby) >= 1:
            scene = _build_scene(dem, [peak] + nearby[:4], res_m)
            if scene:
                scenes.append(scene)

    # Strategy 2: Peak pairs (double peak skylines)
    for i, p1 in enumerate(feature_set.peaks[:10]):
        for p2 in feature_set.peaks[i + 1:10]:
            dist = np.sqrt((p1.row - p2.row) ** 2 + (p1.col - p2.col) ** 2)
            if dist < max_span_px:
                scene = _build_scene(dem, [p1, p2], res_m, scene_type="double_peak")
                if scene:
                    scenes.append(scene)

    # Strategy 3: Cliff + valley floor (vertical drama)
    cliff_features = _cliff_features(feature_set.cliffs, dem, res_m)
    for cliff in cliff_features[:10]:
        nearby = _find_nearby(cliff, all_features, max_span_px)
        scene = _build_scene(dem, [cliff] + nearby[:3], res_m, scene_type="cliff_valley")
        if scene:
            scenes.append(scene)

    # Strategy 4: Water + peak (classic reflection)
    lake_features = _lake_features(feature_set.lakes, dem)
    for lake in lake_features[:5]:
        nearby_peaks = [f for f in _find_nearby(lake, all_features, max_span_px)
                        if f.type == "peak"]
        if nearby_peaks:
            scene = _build_scene(dem, [lake, nearby_peaks[0]], res_m, scene_type="peak_lake")
            if scene:
                scenes.append(scene)

    # Deduplicate scenes that share too many features
    before_dedup = len(scenes)
    scenes = _deduplicate(scenes)
    log.info(f"Created {len(scenes)} scenes ({before_dedup} before dedup)")
    log.debug(f"Scene types: {dict((t, sum(1 for s in scenes if s.scene_type == t)) for t in set(s.scene_type for s in scenes))}" if scenes else "")

    return scenes[:100]  # cap at 100 scenes


def _collect_all_features(fs: FeatureSet, dem: np.ndarray) -> List[Feature]:
    """Collect all point features into a single list."""
    features = list(fs.peaks) + list(fs.saddles)
    features += _cliff_features(fs.cliffs, dem)
    features += _lake_features(fs.lakes, dem)
    return features


def _cliff_features(cliff_mask: np.ndarray, dem: np.ndarray, res_m: float = 75) -> List[Feature]:
    """Convert cliff mask to representative point features."""
    from scipy.ndimage import label
    labeled, n = label(cliff_mask)
    features = []
    for i in range(1, min(n + 1, 20)):
        rows, cols = np.where(labeled == i)
        if len(rows) < 5:
            continue
        r, c = int(np.mean(rows)), int(np.mean(cols))
        features.append(Feature(
            type="cliff", row=r, col=c,
            elevation=dem[r, c],
            strength=len(rows) * res_m,  # cliff extent in meters
        ))
    return features


def _lake_features(lake_mask: np.ndarray, dem: np.ndarray) -> List[Feature]:
    """Convert lake mask to representative point features."""
    from scipy.ndimage import label
    labeled, n = label(lake_mask)
    features = []
    for i in range(1, min(n + 1, 10)):
        rows, cols = np.where(labeled == i)
        if len(rows) < 10:
            continue
        r, c = int(np.mean(rows)), int(np.mean(cols))
        features.append(Feature(
            type="lake", row=r, col=c,
            elevation=dem[r, c],
            strength=len(rows),  # lake area in pixels
        ))
    return features


def _find_nearby(
    anchor: Feature, candidates: List[Feature], max_dist_px: float
) -> List[Feature]:
    """Find features near an anchor, sorted by distance."""
    nearby = []
    for f in candidates:
        if f.row == anchor.row and f.col == anchor.col:
            continue
        dist = np.sqrt((f.row - anchor.row) ** 2 + (f.col - anchor.col) ** 2)
        if dist < max_dist_px:
            nearby.append((dist, f))
    nearby.sort(key=lambda x: x[0])
    return [f for _, f in nearby]


def _build_scene(
    dem: np.ndarray,
    features: List[Feature],
    res_m: float,
    scene_type: str = "mixed",
) -> Scene:
    """Build a Scene from a list of features."""
    if len(features) < 1:
        return None

    rows = [f.row for f in features]
    cols = [f.col for f in features]
    center_r = int(np.mean(rows))
    center_c = int(np.mean(cols))

    span = np.sqrt(
        (max(rows) - min(rows)) ** 2 + (max(cols) - min(cols)) ** 2
    )

    # Auto-detect scene type from feature composition
    if scene_type == "mixed":
        types = {f.type for f in features}
        if "peak" in types and "lake" in types:
            scene_type = "peak_lake"
        elif sum(1 for f in features if f.type == "peak") >= 2:
            scene_type = "double_peak"
        elif "cliff" in types:
            scene_type = "cliff_valley"
        else:
            scene_type = "mixed"

    # 3D positions: (row_m, col_m, elevation)
    anchor_3d = [
        (f.row * res_m, f.col * res_m, f.elevation)
        for f in features
    ]

    return Scene(
        features=features,
        center_row=center_r,
        center_col=center_c,
        center_elevation=dem[center_r, center_c],
        scene_type=scene_type,
        span_pixels=span,
        anchor_positions_3d=anchor_3d,
    )


def _deduplicate(scenes: List[Scene], min_dist_px: float = 20) -> List[Scene]:
    """Remove scenes whose centers are too close together."""
    kept = []
    for scene in scenes:
        is_dup = False
        for existing in kept:
            dist = np.sqrt(
                (scene.center_row - existing.center_row) ** 2 +
                (scene.center_col - existing.center_col) ** 2
            )
            if dist < min_dist_px:
                is_dup = True
                break
        if not is_dup:
            kept.append(scene)
    return kept
