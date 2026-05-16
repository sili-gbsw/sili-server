"""F-01. 공정 데이터 수집 — REST 엔드포인트.

- POST /api/v1/weld-events : 타점 데이터 수신 + 즉시 판정 (PLC 게이트웨이)

판정 결과(`judgement`) 는 F-04/F-05 구현 전까지는 null 로 응답된다.
이력 조회(GET) 는 F-09 (이력·추적성) 범위라 별도 구현된다.
"""

from fastapi import APIRouter, status

from app.core.response import ApiResponse, success_response
from app.schemas.weld_event import WeldEventCreate, WeldEventRead
from app.services.weld_event_service import ingest_weld_event

router = APIRouter(prefix="/weld-events", tags=["weld-events"])


@router.post(
    "",
    response_model=ApiResponse[WeldEventRead],
    status_code=status.HTTP_201_CREATED,
    summary="타점 데이터 수신 + 즉시 판정 (PLC)",
)
async def post_weld_event(payload: WeldEventCreate):
    event = await ingest_weld_event(payload.model_dump(mode="json"))
    return success_response(
        data=WeldEventRead.from_document(event).model_dump(mode="json"),
        message="OK",
        code=201,
    )
