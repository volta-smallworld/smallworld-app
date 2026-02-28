"""
FastAPI backend for smallworld.

Endpoints:
  POST /api/analyze     — run the full pipeline for a location
  POST /api/chat        — agent conversational interface
  GET  /api/dem         — fetch raw DEM data for a location
  POST /api/export/csv  — export viewpoints as Litchi drone CSV
"""

import sys
import os
import json
import traceback
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from pipeline import PipelineConfig, run_pipeline, export_litchi_csv, ViewpointResult
from agent.chat import AgentChat
from terrain.fetch import fetch_dem, pixel_to_lat_lng
from log import get_logger, setup_logging


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def numpy_safe(obj):
    """Recursively convert numpy types in a dict/list to native Python types."""
    if isinstance(obj, dict):
        return {k: numpy_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [numpy_safe(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj

log = get_logger("main")

setup_logging()

app = FastAPI(
    title="smallworld",
    description="Algorithmic photography angle finder",
    version="0.1.0",
)

# Serve rendered images as static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(os.path.join(static_dir, "renders"), exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

log.info("smallworld backend starting up")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global agent instance (maintains conversation history per session)
agent = AgentChat()

# Cache for last pipeline results (simple in-memory, per session)
last_results: List[ViewpointResult] = []


# ── Request/Response Models ────────────────────────────────

class AnalyzeRequest(BaseModel):
    center_lat: float
    center_lng: float
    radius_km: float = 10.0
    mode: str = "ground"
    camera_height_m: float = 1.7
    feature_weights: Optional[Dict[str, float]] = None
    beauty_weights: Optional[Dict[str, float]] = None
    composition_filter: Optional[List[str]] = None
    max_results: int = 20
    compute_lighting: bool = True


class ChatRequest(BaseModel):
    message: str


class ExportRequest(BaseModel):
    viewpoint_indices: Optional[List[int]] = None  # 1-indexed, None = all


class DEMRequest(BaseModel):
    center_lat: float
    center_lng: float
    radius_km: float = 10.0
    zoom: int = 12


# ── Endpoints ──────────────────────────────────────────────

@app.get("/")
def root():
    return {"app": "smallworld", "status": "running"}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    """Run the full pipeline for a location."""
    global last_results

    log.info(f"POST /api/analyze: ({req.center_lat:.4f}, {req.center_lng:.4f}) "
             f"r={req.radius_km}km mode={req.mode}")

    try:
        config = PipelineConfig(
            center_lat=req.center_lat,
            center_lng=req.center_lng,
            radius_km=req.radius_km,
            mode=req.mode,
            camera_height_m=req.camera_height_m,
            feature_weights=req.feature_weights or {},
            beauty_weights=req.beauty_weights or {},
            composition_filter=req.composition_filter,
            max_results=req.max_results,
            compute_lighting=req.compute_lighting,
        )

        results = run_pipeline(config)
        last_results = results

        log.info(f"Analyze complete: {len(results)} viewpoints returned")

        return numpy_safe({
            "status": "success",
            "count": len(results),
            "viewpoints": [r.to_dict() for r in results],
        })

    except Exception as e:
        log.error(f"Analyze failed: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
def chat(req: ChatRequest):
    """Agent conversational interface."""
    log.info(f"POST /api/chat: {req.message[:80]}{'...' if len(req.message) > 80 else ''}")
    def pipeline_runner(config_dict: dict) -> list:
        config = PipelineConfig(
            center_lat=config_dict.get("center_lat", 0),
            center_lng=config_dict.get("center_lng", 0),
            radius_km=config_dict.get("radius_km", 10),
            mode=config_dict.get("mode", "ground"),
            feature_weights=config_dict.get("feature_weights", {}),
            beauty_weights=config_dict.get("beauty_weights", {}),
            composition_filter=config_dict.get("composition_filter"),
            max_results=config_dict.get("max_results", 10),
            compute_lighting=config_dict.get("compute_lighting", True),
        )
        return run_pipeline(config)

    result = agent.chat(req.message, pipeline_runner=pipeline_runner)

    return {
        "response": result["response"],
        "results": result.get("results"),
    }


@app.post("/api/export/csv", response_class=PlainTextResponse)
def export_csv(req: ExportRequest):
    """Export viewpoints as Litchi-compatible CSV."""
    global last_results
    log.info(f"POST /api/export/csv: indices={req.viewpoint_indices}")

    if not last_results:
        raise HTTPException(status_code=400, detail="No results to export. Run /api/analyze first.")

    if req.viewpoint_indices:
        selected = [last_results[i - 1] for i in req.viewpoint_indices
                     if 0 < i <= len(last_results)]
    else:
        selected = last_results

    csv = export_litchi_csv(selected)
    return csv


@app.post("/api/dem")
def get_dem(req: DEMRequest):
    """Fetch raw DEM data for visualization."""
    log.info(f"POST /api/dem: ({req.center_lat:.4f}, {req.center_lng:.4f}) "
             f"r={req.radius_km}km zoom={req.zoom}")
    try:
        dem, metadata = fetch_dem(
            req.center_lat, req.center_lng,
            req.radius_km, req.zoom,
        )

        # Downsample for transfer (max 256x256)
        h, w = dem.shape
        step = max(1, max(h, w) // 256)
        downsampled = dem[::step, ::step]

        return numpy_safe({
            "elevation": downsampled.tolist(),
            "metadata": metadata,
            "shape": list(downsampled.shape),
            "min_elevation": float(dem.min()),
            "max_elevation": float(dem.max()),
        })

    except Exception as e:
        log.error(f"DEM fetch failed: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
