from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    terrarium_tile_url_template: str = (
        "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
    )
    default_terrarium_zoom: int = 12
    max_tiles_per_request: int = 36

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

    model_config = {"env_file": ".env"}


settings = Settings()
