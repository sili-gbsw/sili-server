from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.openapi import setup_openapi
from app.core.response import ApiResponse, success_response
from app.db.session import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.PROJECT_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

register_exception_handlers(app)
setup_openapi(app)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get(
    "/",
    response_model=ApiResponse[dict],
    tags=["health"],
    summary="헬스 체크",
)
def read_root():
    return success_response(
        data={"service": settings.PROJECT_NAME, "version": settings.PROJECT_VERSION},
        message="Hello, FastAPI!",
    )
