"""F-10. 설정(Config) 관리 — REST 엔드포인트.

- GET    /api/v1/config         : 현재 설정(싱글톤) 조회. 없으면 기본값으로 시드.
- PATCH  /api/v1/config         : 부분 갱신 + audit 기록. (관리자 권한, v1은 헤더 기반)
- GET    /api/v1/config/audit   : 변경 이력 조회 (최신순).
"""

from fastapi import APIRouter, Header, Query

from app.core.response import ApiResponse, success_response
from app.schemas.config import ConfigAuditRead, ConfigRead, ConfigUpdate
from app.services.config_service import (
    get_or_init_config,
    list_audits,
    update_config,
)

router = APIRouter(prefix="/config", tags=["config"])


@router.get(
    "",
    response_model=ApiResponse[ConfigRead],
    summary="시스템 설정 조회",
)
async def get_config():
    config = await get_or_init_config()
    return success_response(
        data=ConfigRead.from_document(config).model_dump(mode="json")
    )


@router.patch(
    "",
    response_model=ApiResponse[ConfigRead],
    summary="시스템 설정 부분 갱신 (admin)",
)
async def patch_config(
    payload: ConfigUpdate,
    changed_by: str = Header(default="system", alias="X-Changed-By"),
):
    updates = payload.model_dump(exclude_unset=True, mode="json")
    config = await update_config(updates=updates, changed_by=changed_by)
    return success_response(
        data=ConfigRead.from_document(config).model_dump(mode="json"),
        message="시스템 설정 부분이 갱신되었습니다.",
    )


@router.get(
    "/audit",
    response_model=ApiResponse[list[ConfigAuditRead]],
    summary="설정 변경 이력 조회",
)
async def get_config_audit(
    limit: int = Query(default=100, ge=1, le=500),
):
    docs = await list_audits(limit=limit)
    return success_response(
        data=[ConfigAuditRead.from_document(d).model_dump(mode="json") for d in docs]
    )
