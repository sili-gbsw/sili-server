from fastapi import APIRouter

from app.api.v1 import (
    config,
    exports,
    judgements,
    learning,
    notifications,
    parts,
    reinspection,
    weld_events,
)

api_router = APIRouter()
api_router.include_router(config.router)
api_router.include_router(parts.router)
api_router.include_router(weld_events.router)
api_router.include_router(reinspection.router)
api_router.include_router(judgements.router)
api_router.include_router(exports.router)
api_router.include_router(notifications.router)
api_router.include_router(learning.router)
