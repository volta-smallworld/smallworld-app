import os

# AWS Terrain Tiles (free, no key needed)
TERRAIN_TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"

# Anthropic API for agent
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Defaults
DEFAULT_RADIUS_KM = 10
DEFAULT_ZOOM = 12  # ~75m resolution, good balance of speed and detail
MIN_ZOOM = 10
MAX_ZOOM = 14  # ~19m resolution

# Camera defaults
DEFAULT_FOV_DEG = 60
DEFAULT_CAMERA_HEIGHT_M = 1.7  # standing photographer
DRONE_MIN_ALT_M = 30
DRONE_MAX_ALT_M = 400

# Scoring weights (defaults, user-adjustable)
DEFAULT_FEATURE_WEIGHTS = {
    "peaks": 0.7,
    "ridges": 0.5,
    "cliffs": 0.6,
    "water": 0.6,
    "relief": 0.5,
}

DEFAULT_BEAUTY_WEIGHTS = {
    "viewshed_richness": 0.20,
    "viewpoint_entropy": 0.15,
    "skyline_fractal": 0.20,
    "prospect_refuge": 0.15,
    "depth_layering": 0.10,
    "mystery": 0.10,
    "water_visibility": 0.10,
}

# Fractal dimension target
TARGET_FRACTAL_DIM = 1.3
FRACTAL_DIM_SIGMA = 0.15

# Lighting
SHADOW_RATIO_IDEAL = 0.35
SUN_ELEVATION_IDEAL_DEG = 8.0
LIGHTING_SAMPLE_INTERVAL_MIN = 15
