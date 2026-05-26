from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.openapi import setup_openapi
from app.core.response import ApiResponse, success_response
from app.db.session import close_db, init_db
from app.services.config_seed import seed_default_config
from app.services.user_seed import seed_default_admin


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await seed_default_config()
    await seed_default_admin()
    try:
        yield
    finally:
        await close_db()


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
