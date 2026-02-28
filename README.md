# Smallworld

Terrain analysis platform. Click a point on the globe, set a radius, and fetch decoded elevation data from AWS Terrarium tiles.

## Prerequisites

- [Node.js](https://nodejs.org/) 20+
- [pnpm](https://pnpm.io/) 9+
- [Python](https://www.python.org/) 3.12+
- [uv](https://docs.astral.sh/uv/)

## Setup

### Web (Next.js)

```bash
pnpm install
```

### API (FastAPI)

```bash
cd apps/api
uv sync
```

## Running locally

Start the API and web app in separate terminals:

```bash
# Terminal 1 — API on http://localhost:8000
pnpm dev:api

# Terminal 2 — Web on http://localhost:3000
pnpm dev:web
```

## Testing

```bash
# Backend tests
pnpm test:api
```

## Example API request

```bash
curl -X POST http://localhost:8000/api/v1/terrain/elevation-grid \
  -H "Content-Type: application/json" \
  -d '{
    "center": { "lat": 39.7392, "lng": -104.9903 },
    "radiusMeters": 5000
  }'
```

Example response:

```json
{
  "request": {
    "center": { "lat": 39.7392, "lng": -104.9903 },
    "radiusMeters": 5000,
    "zoomUsed": 12
  },
  "bounds": {
    "north": 39.7841,
    "south": 39.6943,
    "east": -104.9321,
    "west": -105.0485
  },
  "grid": {
    "width": 128,
    "height": 128,
    "cellSizeMetersApprox": 78.1,
    "elevations": [[1609.2, 1610.0]]
  },
  "tiles": [
    { "z": 12, "x": 852, "y": 1552 }
  ],
  "stats": {
    "minElevation": 1532.4,
    "maxElevation": 2488.9,
    "meanElevation": 1921.7
  },
  "source": "aws-terrarium"
}
```
