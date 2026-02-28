from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from smallworld_api.config import settings
from smallworld_api.routes.previews import router as previews_router
from smallworld_api.routes.terrain import router as terrain_router

app = FastAPI(title="Smallworld API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(terrain_router, prefix="/api/v1/terrain")
app.include_router(previews_router, prefix="/api/v1/previews")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
