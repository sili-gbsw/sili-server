from fastapi import APIRouter

from app.api.v1 import config

api_router = APIRouter()
api_router.include_router(config.router)
