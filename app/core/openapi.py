from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.core.config import settings

TAGS_METADATA: list[dict[str, Any]] = [
    {"name": "health", "description": "서버 상태 확인"},
    {"name": "config", "description": "시스템 설정 조회/변경 및 변경 이력 (F-10)"},
    {"name": "parts", "description": "부품 마스터 CRUD (F-02)"},
    {
        "name": "weld-events",
        "description": "PLC 타점 데이터 수집 + 판정 호출 (F-01)",
    },
]

_COMMON_ERROR_RESPONSES: dict[str, dict[str, Any]] = {
    "400": {"description": "Bad Request"},
    "404": {"description": "Not Found"},
    "422": {"description": "Validation Error"},
    "500": {"description": "Internal Server Error"},
}


def setup_openapi(app: FastAPI) -> None:
    """Inject project metadata and common error responses into the OpenAPI schema."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=settings.PROJECT_NAME,
            version=settings.PROJECT_VERSION,
            description=settings.PROJECT_DESCRIPTION,
            routes=app.routes,
            tags=TAGS_METADATA,
        )

        for path in schema.get("paths", {}).values():
            for operation in path.values():
                if not isinstance(operation, dict):
                    continue
                responses = operation.setdefault("responses", {})
                for code, body in _COMMON_ERROR_RESPONSES.items():
                    responses.setdefault(code, body)

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[assignment]
