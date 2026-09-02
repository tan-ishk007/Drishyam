"""Standalone FastAPI application entry point; it does not import or mount the DRISHYAM frontend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
settings = get_settings()

app = FastAPI(
    title="NyayTrace / DRISHYAM Backend API",
    version="0.1.0",
    description="Standalone cybercrime evidence intelligence backend. No frontend integration is mounted.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "drishyam-backend", "environment": settings.environment}


app.include_router(api_router, prefix=settings.api_v1_prefix)
