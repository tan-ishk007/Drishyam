"""Top-level versioned router; individual modules are registered after their implementation."""

from fastapi import APIRouter

from app.api import account, analysis, assistant, auth, cases, claims, evidence, export, gmail_oauth, grounded, ledger, notes, notifications, preview, review

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(assistant.router)
api_router.include_router(account.router)
api_router.include_router(gmail_oauth.router)
api_router.include_router(cases.router)
api_router.include_router(evidence.router)
api_router.include_router(analysis.router)
api_router.include_router(claims.router)
api_router.include_router(notifications.router)
api_router.include_router(review.router)
api_router.include_router(grounded.router)
api_router.include_router(ledger.router)
api_router.include_router(notes.router)
api_router.include_router(export.router)
api_router.include_router(preview.router)
