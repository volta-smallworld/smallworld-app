"""
Pipeline orchestrator: runs all phases from terrain fetch to final results.

10B viewpoints → ~500 deterministic → ~50 scored → ~10 delivered
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from terrain.fetch import fetch_dem, pixel_to_lat_lng
from terrain.analysis import compute_derivatives
from terrain.features import extract_features
from terrain.interest import compute_interest_map
from camera.scenes import group_scenes
from camera.solver import solve_camera_poses, CameraPose
from camera.fractal import compute_fractal_distance
from scoring.beauty import score_beauty, BeautyScores
from scoring.lighting import compute_optimal_lighting, LightingResult
from renderer.render import render_viewpoint, render_overview
from config import DEFAULT_FEATURE_WEIGHTS, DEFAULT_BEAUTY_WEIGHTS
from log import get_logger, log_phase

log = get_logger("pipeline")


@dataclass
class ViewpointResult:
    """A final scored viewpoint ready for delivery."""
    rank: int
    lat: float
    lng: float
    altitude_m: float
    height_above_ground_m: float
    heading_deg: float
    pitch_deg: float
    fov_deg: float
    composition: str
    scene_type: str
    beauty_scores: dict
    beauty_total: float
    lighting: Optional[dict] = None
    render_url: Optional[str] = None

    def to_dict(self):
        return {
            "rank": self.rank,
            "lat": round(self.lat, 6),
            "lng": round(self.lng, 6),
            "altitude_m": round(self.altitude_m, 1),
            "height_above_ground_m": round(self.height_above_ground_m, 1),
            "heading_deg": round(self.heading_deg, 1),
            "pitch_deg": round(self.pitch_deg, 1),
            "fov_deg": round(self.fov_deg, 1),
            "composition": self.composition,
            "scene_type": self.scene_type,
            "beauty_scores": self.beauty_scores,
            "beauty_total": round(self.beauty_total, 3),
            "lighting": self.lighting,
            "render_url": self.render_url,
        }


@dataclass
class PipelineConfig:
    """Configuration for a pipeline run."""
    center_lat: float
    center_lng: float
    radius_km: float = 10.0
    zoom: int = 12
    mode: str = "ground"  # "ground" or "drone"
    camera_height_m: float = 1.7
    feature_weights: dict = field(default_factory=lambda: dict(DEFAULT_FEATURE_WEIGHTS))
    beauty_weights: dict = field(default_factory=lambda: dict(DEFAULT_BEAUTY_WEIGHTS))
    composition_filter: List[str] = None
    max_results: int = 20
    compute_lighting: bool = True


@dataclass
class PipelineProgress:
    """Progress tracking for the pipeline."""
    phase: str = ""
    progress: float = 0.0
    message: str = ""


def run_pipeline(config: PipelineConfig, progress_callback=None) -> List[ViewpointResult]:
    """Run the full smallworld pipeline.

    Phase 1: Fetch DEM + extract terrain features
    Phase 2: Group features into scenes
    Phase 3: Compute camera positions (deterministic)
    Phase 4: Score for beauty (DEM-based, no rendering)
    Phase 5: Render 3D terrain views from each viewpoint
    Phase 7: Compute optimal lighting time (optional)
    """

    def update(phase, progress, message):
        log.info(f"[{phase}] ({progress:.0%}) {message}")
        if progress_callback:
            progress_callback(PipelineProgress(phase, progress, message))

    # ── Phase 1: Terrain Analysis ──────────────────────────────
    with log_phase(log, "Phase 1: Terrain Analysis"):
        update("terrain", 0.0, "Fetching DEM tiles...")

        dem, metadata = fetch_dem(
            config.center_lat, config.center_lng,
            config.radius_km, config.zoom,
        )
        res_m = metadata["resolution_m"]
        log.info(f"DEM grid: {dem.shape}, resolution: {res_m:.1f}m/px, "
                 f"elevation: {dem.min():.0f}–{dem.max():.0f}m")

        update("terrain", 0.3, "Computing terrain derivatives...")
        derivatives = compute_derivatives(dem, res_m)

        update("terrain", 0.6, "Extracting features...")
        features = extract_features(dem, derivatives, res_m)

        update("terrain", 0.8, "Computing interest map...")
        interest_map = compute_interest_map(
            dem, features, derivatives, config.feature_weights,
        )

        log.info(f"Features: {len(features.peaks)} peaks, "
                 f"{features.ridgelines.sum()} ridge cells, "
                 f"{len(features.saddles)} saddles, "
                 f"{features.lakes.sum()} lake cells")

    # ── Phase 2: Scene Grouping ────────────────────────────────
    with log_phase(log, "Phase 2: Scene Grouping"):
        scenes = group_scenes(dem, features, res_m)
        log.info(f"Created {len(scenes)} photographable scenes")

        if not scenes:
            log.warning("No scenes found — returning empty results")
            return []

    # ── Phase 3: Camera Computation ────────────────────────────
    with log_phase(log, "Phase 3: Camera Computation"):
        camera_height = config.camera_height_m

        poses = solve_camera_poses(
            scenes, dem, res_m,
            camera_height_m=camera_height,
            mode=config.mode,
            composition_filter=config.composition_filter,
        )
        log.info(f"Inverse PnP solver: {len(poses)} poses from {len(scenes)} scenes")

        # Add fractal dimension candidates at a few heights
        fractal_candidates = compute_fractal_distance(
            dem, features.ridgelines, res_m,
        )
        fractal_heights = [15, 50] if config.mode == "drone" else [camera_height]
        fractal_added = 0
        for fc in fractal_candidates:
            for fh in fractal_heights:
                cam_row = int(fc.row + fc.normal_direction[0] * fc.distance_m / res_m)
                cam_col = int(fc.col + fc.normal_direction[1] * fc.distance_m / res_m)
                h, w = dem.shape
                if 0 <= cam_row < h and 0 <= cam_col < w:
                    ground_z = dem[cam_row, cam_col]
                    cam_z = ground_z + fh
                    # Compute pitch toward the ridge feature
                    feat_z = dem[min(fc.row, h-1), min(fc.col, w-1)]
                    dz = feat_z - cam_z
                    horiz_dist = fc.distance_m
                    pitch = np.degrees(np.arctan2(dz, max(horiz_dist, 1)))
                    yaw = np.degrees(np.arctan2(
                        -fc.normal_direction[1], -fc.normal_direction[0]
                    )) % 360
                    poses.append(CameraPose(
                        x=cam_col * res_m, y=cam_row * res_m, z=cam_z,
                        pitch=pitch, yaw=yaw, fov=60,
                        composition="fractal_optimal",
                        scene_type="ridge",
                        row=cam_row, col=cam_col,
                    ))
                    fractal_added += 1

        log.info(f"Fractal candidates: {len(fractal_candidates)} analyzed, "
                 f"{fractal_added} added → {len(poses)} total candidates")

        if not poses:
            log.warning("No camera poses found — returning empty results")
            return []

        # Cap candidates to keep scoring fast (~500 max)
        max_candidates = 500
        if len(poses) > max_candidates:
            log.info(f"Capping {len(poses)} candidates to {max_candidates} (random sample)")
            rng = np.random.RandomState(0)
            indices = rng.choice(len(poses), max_candidates, replace=False)
            poses = [poses[i] for i in indices]

    # ── Phase 4: Beauty Scoring ────────────────────────────────
    with log_phase(log, "Phase 4: Beauty Scoring"):
        water_mask = features.lakes | (features.streams > np.percentile(features.streams, 95))

        scored = []
        for i, pose in enumerate(poses):
            if i % 20 == 0:
                update("scoring", i / len(poses),
                       f"Scoring viewpoint {i+1}/{len(poses)}...")

            beauty = score_beauty(
                dem, pose.row, pose.col, pose.z, res_m,
                interest_map, water_mask,
                fov_deg=pose.fov, yaw_deg=pose.yaw,
                weights=config.beauty_weights,
            )
            scored.append((pose, beauty))

        scored.sort(key=lambda x: x[1].total, reverse=True)

        # Spatial diversity: don't return multiple results from the same spot
        # Require minimum distance between selected viewpoints
        min_sep_pixels = max(20, min(dem.shape) * 0.03)  # ~3% of DEM extent
        top = []
        for pose, beauty in scored:
            too_close = False
            for existing_pose, _ in top:
                dist = np.sqrt((pose.row - existing_pose.row)**2 +
                               (pose.col - existing_pose.col)**2)
                if dist < min_sep_pixels:
                    too_close = True
                    break
            if not too_close:
                top.append((pose, beauty))
            if len(top) >= config.max_results:
                break

        if top:
            log.info(f"Top {len(top)} of {len(scored)} scored (min_sep={min_sep_pixels:.0f}px) — "
                     f"best: {top[0][1].total:.3f}, worst: {top[-1][1].total:.3f}")

    # ── Phase 5: Render 3D Terrain Views ──────────────────────
    with log_phase(log, "Phase 5: Terrain Rendering"):
        import hashlib, time
        run_id = hashlib.md5(
            f"{config.center_lat},{config.center_lng},{time.time()}".encode()
        ).hexdigest()[:8]

        # Only render top 10 to keep pipeline fast (~1.5s each)
        max_renders = min(10, len(top))
        render_filenames = []
        for rank, (pose, beauty) in enumerate(top):
            if rank < max_renders:
                update("rendering", rank / max_renders,
                       f"Rendering viewpoint {rank+1}/{max_renders}...")

                render_id = f"{run_id}_vp{rank+1:02d}"
                filename = render_viewpoint(
                    dem, pose.row, pose.col, pose.z,
                    pose.yaw, pose.pitch, pose.fov, res_m,
                    render_id=render_id,
                    width=640, height=400,
                )
                render_filenames.append(filename)
            else:
                render_filenames.append(None)

        # Render overview map
        camera_data = [(p.row, p.col, p.z, p.yaw) for p, _ in top]
        overview_file = render_overview(dem, res_m, camera_data, f"{run_id}_overview")

        rendered_count = sum(1 for f in render_filenames if f)
        log.info(f"Rendered {rendered_count}/{len(top)} viewpoints"
                 f"{' + overview' if overview_file else ''}")

    # ── Phase 7: Lighting (optional) ───────────────────────────
    results = []
    if config.compute_lighting:
        log_ctx = log_phase(log, "Phase 7: Optimal Lighting")
    else:
        from contextlib import nullcontext
        log_ctx = nullcontext()

    with log_ctx:
        for rank, (pose, beauty) in enumerate(top):
            lat, lng = pixel_to_lat_lng(pose.row, pose.col, metadata)

            lighting_dict = None
            if config.compute_lighting:
                update("lighting", rank / len(top),
                       f"Computing lighting for viewpoint {rank+1}...")

                from scoring.viewshed import compute_viewshed
                viewshed = compute_viewshed(dem, pose.row, pose.col, pose.z, res_m)

                lighting = compute_optimal_lighting(
                    dem, pose.row, pose.col, pose.z, res_m,
                    lat, lng, viewshed,
                )
                lighting_dict = lighting.to_dict()

            # Build render URL if we have a render
            render_url = None
            if render_filenames[rank]:
                render_url = f"/static/renders/{render_filenames[rank]}"

            # Height above ground = camera altitude - terrain elevation
            ground_elev = dem[pose.row, pose.col]
            height_agl = pose.z - ground_elev

            results.append(ViewpointResult(
                rank=rank + 1,
                lat=lat,
                lng=lng,
                altitude_m=pose.z,
                height_above_ground_m=height_agl,
                heading_deg=pose.yaw,
                pitch_deg=pose.pitch,
                fov_deg=pose.fov,
                composition=pose.composition,
                scene_type=pose.scene_type,
                beauty_scores=beauty.to_dict(),
                beauty_total=beauty.total,
                lighting=lighting_dict,
                render_url=render_url,
            ))

    log.info(f"Pipeline complete: {len(results)} viewpoints delivered")
    update("complete", 1.0, f"Done! {len(results)} viewpoints found.")

    return results


def export_litchi_csv(results: List[ViewpointResult]) -> str:
    """Export viewpoints as Litchi-compatible CSV for drone missions.

    Viewpoints ordered by nearest-neighbor TSP to minimize flight distance.
    """
    if not results:
        return ""

    # Sort by nearest neighbor TSP
    ordered = _nearest_neighbor_tsp(results)

    header = (
        "latitude,longitude,altitude(m),heading(deg),curvesize(m),"
        "rotationdir(0),gimbalmode(2),gimbalpitchangle(deg),"
        "actiontype1(1),actionparam1(0),altitudemode(1)"
    )

    rows = [header]
    for vp in ordered:
        rows.append(
            f"{vp.lat},{vp.lng},{vp.altitude_m},{vp.heading_deg},"
            f"0,0,2,{vp.pitch_deg},1,0,1"
        )

    return "\n".join(rows)


def _nearest_neighbor_tsp(results: List[ViewpointResult]) -> List[ViewpointResult]:
    """Simple nearest-neighbor ordering to minimize total flight distance."""
    if len(results) <= 2:
        return results

    remaining = list(results)
    ordered = [remaining.pop(0)]

    while remaining:
        current = ordered[-1]
        best_dist = float('inf')
        best_idx = 0

        for i, r in enumerate(remaining):
            dist = np.sqrt(
                (r.lat - current.lat)**2 + (r.lng - current.lng)**2
            )
            if dist < best_dist:
                best_dist = dist
                best_idx = i

        ordered.append(remaining.pop(best_idx))

    return ordered
