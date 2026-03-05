# DEM Upgrade Research: Terrarium → Copernicus GLO-30

**Status**: Future roadmap
**Date**: 2026-03-03

## Current State: AWS Terrarium Tiles

- **Source data**: Blend from Tilezen/joerd (~2018, effectively frozen) — SRTM 30m globally, 3DEP 3–10m in the US
- **URL**: `s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`
- **Encoding**: `R*256 + G + B/256 - 32768` → meters (PNG, 256x256 tiles)
- **Zoom 12** (grid default): ~38m/pixel — undersamples the 30m SRTM data
- **Zoom 14** (point sampler): ~9.5m/pixel — oversamples SRTM, captures real detail where 3DEP exists
- **Vertical accuracy**: ~16m absolute / ~6m relative (SRTM). Sub-meter in US where 3DEP is available
- **Maintenance**: Still served on S3, no deprecation notice, but **no data updates since ~2018**
- **Underlying sources** (by priority): 3DEP 3–10m (US), ArcticDEM 5m (>60N), UK LiDAR 2m, Austria 10m, EU-DEM 30m, Norway 10m, CDEM 20–400m (Canada), LINZ 8m (NZ), SRTM 30m (global), GMTED 250m–1km (low zooms), ETOPO1 ~1.8km (ocean)

## Candidate: Copernicus GLO-30

- **Resolution**: 30m (1 arc-second) horizontal posting
- **Vertical accuracy**: ~4m RMSE globally — **~4x better than SRTM's ~16m absolute error**
- **Data vintage**: 2011–2015 (TanDEM-X mission), vs SRTM's 2000 acquisition
- **Coverage**: Near-global (small exclusions in Armenia/Azerbaijan)
- **Type**: Digital Surface Model (DSM) — includes buildings, vegetation, infrastructure
- **License**: Free for all uses including commercial. Attribution required (DLR/Airbus/ESA/EU)
- **Cost**: Free

### Access methods

| Method | Details |
|--------|---------|
| **AWS Open Data S3** | `s3://copernicus-dem-30m/` — Cloud Optimized GeoTIFFs, 1x1 degree tiles. No API key. HTTP range requests supported. |
| Google Earth Engine | Dataset `COPERNICUS/DEM/GLO30`. Free for research. |
| OpenTopography API | RESTful API, bounding box queries. Free API key, 100–300 calls/day. |
| Microsoft Planetary Computer | STAC API access to COGs. |
| Copernicus Data Space | Browser and API access. |

**Best path for us**: AWS S3 COGs — same provider we already use, no auth needed, COG range requests allow reading sub-regions without full tile download.

## Comparison

| | AWS Terrarium (current) | Copernicus GLO-30 |
|---|---|---|
| Vertical accuracy | ~16m abs / ~6m rel | **~4m RMSE** |
| Resolution | 30m | 30m |
| Data vintage | 2000 (SRTM) | **2011–2015** (TanDEM-X) |
| Maintenance | Frozen ~2018 | Active ESA program |
| Cost | Free | Free |
| License | Open (attribution) | Free incl. commercial |
| Access format | Slippy-map PNG tiles | **1x1 degree COG tiles** |
| Dependency | `httpx` + PIL | **`rasterio` (GDAL)** |

## Benefits of migration

1. **~4x better vertical accuracy** — directly reduces camera-inside-terrain failures. The 3-layer AGL defense in ADR 0009 exists partly because DEM accuracy is insufficient; better data reduces false violations.
2. **15 years newer data** — captures terrain changes since SRTM's 2000 acquisition.
3. **Actively maintained** by ESA with clear institutional backing.
4. **No RGB encode/decode** — COGs contain raw float elevation values.
5. **HTTP range requests on COGs** — can read sub-regions of a 1x1 degree tile without downloading the whole file.

## Costs / risks

- **GDAL dependency**: `rasterio` pulls in `libgdal`, which is notoriously painful in CI/Docker. This is the biggest friction point.
- **Tile indexing change**: From `z/x/y` slippy-map to `{N|S}{lat}/{E|W}{lng}` 1-degree grid. Fetch logic rework needed.
- **DSM vs DTM**: GLO-30 includes buildings/vegetation. For camera safety this is arguably better (don't crash into buildings), but for terrain analysis it may differ from expectations.
- **Larger tiles**: 1x1 degree COGs are bigger than 256px PNG tiles. Need to validate latency for range requests.

## Other alternatives considered

| Option | Lift | Benefit | Drawback |
|--------|------|---------|----------|
| **AWS GeoTIFF tiles** (`/geotiff/` same S3 bucket) | Minimal — same URL pattern | Eliminates RGB decode, 512x512 tiles | Same frozen SRTM data |
| **Bump grid zoom to 13–14** (keep Terrarium) | Config change only | Better utilizes 30m data (~19m/px at z13) | Still SRTM accuracy, more tiles per request |
| **Self-host Open Topo Data + Copernicus** | Medium — Docker + ~20GB storage | Free, no rate limits, point-query API | Another service to operate |
| **Mapbox Terrain-DEM v1** | Drop-in (slippy-map tiles) | Same format, better compression | Proprietary, API key required, same SRTM data |
| **Google Elevation API** | Minimal code | No tile management | $5/1000 req, 32 calls per 128x128 grid, proprietary |
| **Cesium World Terrain** | Not practical | High-res LiDAR in some areas | Quantized mesh format, not designed for grid extraction |

## Recommended migration path

### Phase 1 (near-term, config-only)
Bump `DEFAULT_TERRARIUM_ZOOM` from 12 to 13. ~19m/pixel better samples the underlying 30m SRTM data. May need to adjust `MAX_TILES_PER_REQUEST` cap. No code changes, immediate accuracy improvement.

### Phase 2 (medium-term, Copernicus migration)
1. Add `rasterio` dependency, validate GDAL in Docker/CI
2. Build a COG fetch layer alongside the existing Terrarium fetcher (feature flag)
3. Rework tile indexing for 1-degree grid
4. Update `sample_point_elevation()` to use COG data
5. Validate vertical accuracy improvement against known benchmarks
6. Cut over grid pipeline, deprecate Terrarium fetcher

### Phase 3 (optional, long-term)
Self-host Open Topo Data with Copernicus GLO-30 for sub-millisecond point queries. Eliminates network I/O for camera safety checks.
