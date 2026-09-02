"""Top-level versioned router; individual modules are registered after their implementation."""

from fastapi import APIRouter

from app.api import analysis, auth, cases, claims, evidence, notifications, preview, review

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(cases.router)
api_router.include_router(evidence.router)
api_router.include_router(analysis.router)
api_router.include_router(claims.router)
api_router.include_router(notifications.router)
api_router.include_router(review.router)
api_router.include_router(preview.router)
