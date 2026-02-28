from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    terrarium_tile_url_template: str = (
        "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
    )
    default_terrarium_zoom: int = 12
    max_tiles_per_request: int = 36

    model_config = {"env_file": ".env"}


settings = Settings()
