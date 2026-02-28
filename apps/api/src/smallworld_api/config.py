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

    # ── Preview rendering ─────────────────────────────────────────────────
    preview_artifacts_dir: str = ".preview_artifacts"
    preview_artifact_ttl_hours: int = 24
    preview_renderer_base_url: str = "http://127.0.0.1:3000/render/preview"
    preview_render_timeout_seconds: int = 30
    preview_default_width: int = 1536
    preview_default_height: int = 1024
    preview_default_fov_deg: float = 50.0

    # ── External provider tokens ──────────────────────────────────────────
    cesium_ion_token: str = ""
    mapbox_access_token: str = ""

    # ── Enhancement (Gemini) ──────────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_image_model: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
