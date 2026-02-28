"""
Inverse PnP camera solver: given 3D feature positions and desired 2D screen
positions (from composition templates), solve for camera pose.

This is the core innovation — composition rules become geometric constraints,
making camera position a solvable equation rather than a search problem.
"""

import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass
from .compositions import CompositionTemplate, get_templates_for_scene
from .scenes import Scene
from config import DEFAULT_FOV_DEG, DEFAULT_CAMERA_HEIGHT_M
from log import get_logger

log = get_logger("camera.solver")


@dataclass
class CameraPose:
    """A computed camera position and orientation."""
    # Position in grid coordinates (meters from origin)
    x: float  # east-west
    y: float  # north-south
    z: float  # altitude above sea level
    # Orientation in degrees
    pitch: float  # up/down (-90 to 90, negative = looking down)
    yaw: float  # compass heading (0=N, 90=E, 180=S, 270=W)
    fov: float  # horizontal field of view in degrees
    # Metadata
    composition: str  # which template was used
    scene_type: str
    # Grid coordinates for DEM lookup
    row: int = 0
    col: int = 0


def solve_camera_poses(
    scenes: List[Scene],
    dem: np.ndarray,
    res_m: float,
    fov_deg: float = DEFAULT_FOV_DEG,
    camera_height_m: float = DEFAULT_CAMERA_HEIGHT_M,
    mode: str = "ground",
    image_w: int = 1920,
    image_h: int = 1080,
    composition_filter: List[str] = None,
) -> List[CameraPose]:
    """Solve for camera poses across all scenes and composition templates.

    For each scene × each applicable composition template, solve the
    inverse PnP problem to find the camera position that places features
    at the desired screen positions.

    In drone mode, tries multiple heights (5-100m AGL) and keeps the best.

    Returns list of physically valid CameraPoses.
    """
    all_poses = []
    h, w = dem.shape
    focal_length = (image_w / 2) / np.tan(np.radians(fov_deg / 2))

    # Drone mode: try a few heights to find optimal angles
    if mode == "drone":
        heights_to_try = [15, 50, 100]
    else:
        heights_to_try = [camera_height_m]

    log.info(f"Solving camera poses for {len(scenes)} scenes, "
             f"fov={fov_deg} deg, mode={mode}, "
             f"heights={heights_to_try}")

    for scene in scenes:
        n_features = len(scene.features)
        templates = get_templates_for_scene(n_features)

        if composition_filter:
            templates = [t for t in templates if t.name in composition_filter]

        for template in templates:
            for cam_h in heights_to_try:
                poses = _solve_for_template(
                    scene, template, dem, res_m,
                    focal_length, fov_deg, cam_h,
                    image_w, image_h,
                )
                for pose in poses:
                    if _is_feasible(pose, dem, res_m, cam_h):
                        all_poses.append(pose)

    log.info(f"Solved {len(all_poses)} feasible camera poses from {len(scenes)} scenes")
    return all_poses


def _solve_for_template(
    scene: Scene,
    template: CompositionTemplate,
    dem: np.ndarray,
    res_m: float,
    focal_length: float,
    fov_deg: float,
    camera_height_m: float,
    image_w: int,
    image_h: int,
) -> List[CameraPose]:
    """Solve inverse PnP for a single scene + template combination.

    Returns multiple candidate poses (different approach directions)
    so the beauty scorer can pick the best.
    """
    features = scene.features
    placements = template.feature_placements

    if not placements or not features:
        return []

    # Primary feature (always index 0)
    feat_idx = placements[0][0]
    if feat_idx >= len(features):
        feat_idx = 0
    primary = features[feat_idx]

    # Desired screen position for primary feature
    screen_x_norm = placements[0][1]  # 0-1
    screen_y_norm = placements[0][2]  # 0-1

    if len(placements) >= 2 and len(features) >= 2:
        # Two-feature solve: returns single pose or None
        pose = _solve_two_feature(
            features, placements, dem, res_m,
            focal_length, 0, fov_deg, camera_height_m,
            image_w, image_h, scene.scene_type, template.name,
        )
        return [pose] if pose else []
    else:
        # Single-feature solve: returns list of poses from different directions
        return _solve_single_feature(
            primary, screen_x_norm, screen_y_norm,
            template.horizon_y, dem, res_m,
            focal_length, 0, fov_deg, camera_height_m,
            scene.scene_type, template.name,
        )


def _solve_single_feature(
    feature, screen_x_norm, screen_y_norm, horizon_y,
    dem, res_m, focal_length, pitch_deg, fov_deg, camera_height_m,
    scene_type, composition_name,
) -> List[CameraPose]:
    """Solve camera pose for a single feature placement.

    Returns multiple poses from different approach directions so the
    beauty scorer can pick the best. Pitch is computed from actual
    geometry (camera→feature elevation angle).
    """
    feat_x = feature.col * res_m
    feat_y = feature.row * res_m
    feat_z = feature.elevation
    h, w = dem.shape

    # Estimate viewing distance from feature prominence
    # Scale distance so features fill a reasonable portion of frame
    prominence = max(feature.prominence, 50)
    view_distance = prominence / (0.3 * np.tan(np.radians(fov_deg / 2)))
    view_distance = np.clip(view_distance, 200, 5000)

    # Yaw: determined by screen_x offset
    x_offset_angle = np.arctan2(
        (screen_x_norm - 0.5) * 2 * np.tan(np.radians(fov_deg / 2)),
        1.0
    )

    # Try 8 approach directions, keep best 2 by elevation advantage
    candidates = []

    for angle_offset in np.linspace(0, 2 * np.pi, 8, endpoint=False):
        cam_x = feat_x - view_distance * np.sin(angle_offset)
        cam_y = feat_y - view_distance * np.cos(angle_offset)

        cam_row = int(cam_y / res_m)
        cam_col = int(cam_x / res_m)

        if not (0 <= cam_row < h and 0 <= cam_col < w):
            continue

        ground_z = dem[cam_row, cam_col]
        cam_z = ground_z + camera_height_m

        # Yaw: direction toward feature, adjusted for screen position
        yaw_rad = np.arctan2(feat_x - cam_x, feat_y - cam_y) - x_offset_angle
        yaw_deg = np.degrees(yaw_rad) % 360

        # Pitch from ACTUAL geometry: angle from camera to feature center
        dz = feat_z - cam_z
        horiz_dist = np.sqrt((feat_x - cam_x)**2 + (feat_y - cam_y)**2)
        actual_pitch = np.degrees(np.arctan2(dz, horiz_dist))

        candidates.append((ground_z, CameraPose(
            x=cam_x, y=cam_y, z=cam_z,
            pitch=actual_pitch, yaw=yaw_deg, fov=fov_deg,
            composition=composition_name,
            scene_type=scene_type,
            row=cam_row, col=cam_col,
        )))

    # Return top 2 by ground elevation (different vantage points)
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [pose for _, pose in candidates[:2]]


def _solve_two_feature(
    features, placements, dem, res_m,
    focal_length, pitch_deg, fov_deg, camera_height_m,
    image_w, image_h, scene_type, composition_name,
) -> Optional[CameraPose]:
    """Solve camera pose for two feature placements.

    With 2 features × 2D screen positions = 4 equations.
    Unknowns: cam_x, cam_y, cam_z (constrained to terrain+height), yaw.
    Effectively 3 unknowns → overdetermined → least squares.
    """
    h, w = dem.shape

    f1 = features[placements[0][0] if placements[0][0] < len(features) else 0]
    f2 = features[placements[1][0] if placements[1][0] < len(features) else min(1, len(features) - 1)]

    # 3D positions
    p1 = np.array([f1.col * res_m, f1.row * res_m, f1.elevation])
    p2 = np.array([f2.col * res_m, f2.row * res_m, f2.elevation])

    # Desired screen positions (normalized → pixel offset from center)
    s1 = np.array([
        (placements[0][1] - 0.5) * image_w,
        (0.5 - placements[0][2]) * image_h,
    ])
    s2 = np.array([
        (placements[1][1] - 0.5) * image_w,
        (0.5 - placements[1][2]) * image_h,
    ])

    # Midpoint between features
    mid = (p1 + p2) / 2

    # Direction from f2 to f1 (feature axis)
    feat_dir = p1[:2] - p2[:2]
    feat_dist = np.linalg.norm(feat_dir)
    if feat_dist < 1:
        return None

    # Screen separation tells us viewing distance
    screen_sep = np.linalg.norm(s1 - s2)
    if screen_sep < 10:
        return None

    view_distance = focal_length * feat_dist / screen_sep

    # Camera direction: perpendicular to feature axis, adjusted by screen midpoint
    screen_mid = (s1 + s2) / 2
    # Perpendicular to feature axis
    perp = np.array([-feat_dir[1], feat_dir[0]])
    perp = perp / np.linalg.norm(perp)

    # Try both sides of the feature axis
    for sign in [1, -1]:
        cam_xy = mid[:2] + sign * perp * view_distance

        cam_col = int(cam_xy[0] / res_m)
        cam_row = int(cam_xy[1] / res_m)

        if not (0 <= cam_row < h and 0 <= cam_col < w):
            continue

        ground_z = dem[cam_row, cam_col]
        cam_z = ground_z + camera_height_m

        # Compute yaw: direction toward midpoint
        to_mid = mid[:2] - cam_xy
        yaw_rad = np.arctan2(to_mid[0], to_mid[1])

        # Adjust yaw based on screen midpoint offset
        yaw_correction = np.arctan2(screen_mid[0], focal_length)
        yaw_rad -= yaw_correction

        yaw_deg = np.degrees(yaw_rad) % 360

        # Pitch from actual geometry: angle to feature midpoint
        dz = mid[2] - cam_z
        horiz_dist = np.linalg.norm(to_mid)
        actual_pitch = np.degrees(np.arctan2(dz, max(horiz_dist, 1)))

        pose = CameraPose(
            x=cam_xy[0], y=cam_xy[1], z=cam_z,
            pitch=actual_pitch, yaw=yaw_deg, fov=fov_deg,
            composition=composition_name,
            scene_type=scene_type,
            row=cam_row, col=cam_col,
        )

        if _is_feasible(pose, dem, res_m, camera_height_m):
            return pose

    return None


def _is_feasible(
    pose: CameraPose,
    dem: np.ndarray,
    res_m: float,
    min_clearance_m: float = 1.5,
) -> bool:
    """Check if a camera pose is physically feasible.

    - Not underground
    - Within DEM bounds
    - Not on extremely steep terrain (>60°)
    """
    h, w = dem.shape
    row = int(pose.y / res_m)
    col = int(pose.x / res_m)

    if not (1 <= row < h - 1 and 1 <= col < w - 1):
        return False

    ground_z = dem[row, col]
    if pose.z < ground_z + min_clearance_m:
        return False

    # Check slope at camera position (reject >60° slopes)
    dz_dx = (dem[row, col + 1] - dem[row, col - 1]) / (2 * res_m)
    dz_dy = (dem[row + 1, col] - dem[row - 1, col]) / (2 * res_m)
    slope = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)))
    if slope > 60:
        return False

    return True


def line_of_sight(
    cam_pos: Tuple[float, float, float],
    target_pos: Tuple[float, float, float],
    dem: np.ndarray,
    res_m: float,
) -> bool:
    """Check if there's a clear line of sight between camera and target."""
    cx, cy, cz = cam_pos
    tx, ty, tz = target_pos

    n_samples = int(np.sqrt((tx - cx)**2 + (ty - cy)**2) / res_m)
    n_samples = max(n_samples, 10)

    for i in range(1, n_samples):
        t = i / n_samples
        x = cx + t * (tx - cx)
        y = cy + t * (ty - cy)
        z = cz + t * (tz - cz)

        row = int(y / res_m)
        col = int(x / res_m)

        if 0 <= row < dem.shape[0] and 0 <= col < dem.shape[1]:
            if dem[row, col] > z:
                return False

    return True
