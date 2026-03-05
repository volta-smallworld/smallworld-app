from pathlib import Path

from pydantic_settings import BaseSettings


_CONFIG_FILE = Path(__file__).resolve()
_API_ROOT = _CONFIG_FILE.parents[2]
_REPO_ROOT = _CONFIG_FILE.parents[4]


class Settings(BaseSettings):
    cors_origins: str = "http://localhost:4182,http://127.0.0.1:4182"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    terrarium_tile_url_template: str = (
        "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
    )
    default_terrarium_zoom: int = 13
    max_tiles_per_request: int = 64
    dem_provider: str = "terrarium"
    tile_cache_max_size: int = 512
    tile_cache_ttl_seconds: int = 300

    # Viewpoint settings (hour-three)
    viewpoint_max_returned: int = 12
    viewpoint_max_per_scene: int = 3
    viewpoint_default_fov_degrees: float = 55
    viewpoint_min_clearance_meters: float = 2
    viewpoint_dedup_distance_meters: float = 150
    viewpoint_dedup_heading_degrees: float = 12
    viewpoint_skyline_fd_target: float = 1.3
    viewpoint_skyline_fd_sigma: float = 0.15
    visibility_ray_count: int = 90
    visibility_steps_per_ray: int = 40
    ridge_fractal_scales_meters: str = "150,300,600,1200"
    ridge_default_distance_multiplier: float = 2.5

    # ── Preview rendering ─────────────────────────────────────────────────
    preview_artifacts_dir: str = ".preview_artifacts"
    preview_artifact_ttl_hours: int = 24
    preview_renderer_base_url: str = "http://127.0.0.1:4182/render/preview"
    preview_render_timeout_seconds: int = 30
    preview_default_width: int = 1920
    preview_default_height: int = 1080
    preview_default_fov_deg: float = 50.0

    # ── External provider tokens ──────────────────────────────────────────
    cesium_ion_token: str = ""
    mapbox_access_token: str = ""
    google_maps_api_key: str = ""

    # ── Preview public URL (for MCP artifact URLs) ──────────────────────
    preview_public_base_url: str = ""

    # ── Enhancement (Gemini) ──────────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_image_model: str = "gemini-3.1-flash-image-preview"

    # ── Style Reference ────────────────────────────────────────────────
    style_artifacts_dir: str = ".style_artifacts"
    style_reference_ttl_hours: int = 24
    style_upload_max_bytes: int = 10485760
    style_patch_window_cells: int = 21
    style_patch_stride_cells: int = 8
    style_top_patch_count: int = 24
    style_refinement_iterations: int = 20
    style_refinement_learning_rate: float = 0.15
    style_clip_model_name: str = "ViT-B-32"
    style_clip_pretrained: str = "laion2b_s34b_b79k"
    style_lpips_backbone: str = "alex"
    style_hed_prototxt_path: str = ""
    style_hed_weights_path: str = ""

    # ── Deployment / inter-service ────────────────────────────────────────
    api_internal_url: str = ""  # MCP→API delegation (e.g. http://smallworld-api.railway.internal)
    render_script_path: str = ""  # Override for render-preview.mjs location

    # ── Camera safety / point elevation ──────────────────────────────────
    point_elevation_default_zoom: int = 14
    camera_agl_floor_meters: float = 5.0
    renderer_terrain_clamp_enabled: bool = True
    renderer_terrain_sample_timeout_ms: int = 3000

    model_config = {
        "env_file": (
            str(_REPO_ROOT / ".env"),
            str(_API_ROOT / ".env"),
        ),
        "extra": "ignore",
    }


settings = Settings()
