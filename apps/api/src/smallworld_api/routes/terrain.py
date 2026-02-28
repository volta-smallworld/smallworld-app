import httpx
from fastapi import APIRouter, HTTPException

from smallworld_api.models.terrain import ElevationGridRequest, ElevationGridResponse
from smallworld_api.services.terrarium import get_elevation_grid

router = APIRouter()


@router.post("/elevation-grid", response_model=ElevationGridResponse)
async def elevation_grid(req: ElevationGridRequest):
    try:
        result = await get_elevation_grid(
            lat=req.center.lat,
            lng=req.center.lng,
            radius_m=req.radiusMeters,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream tile fetch failed: {e.response.status_code}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream tile fetch failed: {e}",
        )
    return result
