"""F-06. 재검 큐 관리 — REST 엔드포인트.

- GET  /api/v1/reinspection                    : 큐 목록 (필터: status, part_id)
- GET  /api/v1/reinspection/daily-defects      : 당일 결함 확정 부품 목록 (part_id 그룹)
- GET  /api/v1/reinspection/{queue_id}         : 큐 단건 조회
- POST /api/v1/reinspection/{queue_id}/result  : 재검 결과 등록 → CLOSED 전이
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Query, status

from app.core.exceptions import AppException
from app.core.response import ApiResponse, success_response
from app.models.reinspection import ReinspectionStatus
from app.schemas.reinspection import (
    DailyDefectPartRead,
    ReinspectionRead,
    ReinspectionResultCreate,
)
from app.services.reinspection_service import (
    get_queue,
    list_daily_defect_parts,
    list_queues,
    submit_result,
)

router = APIRouter(prefix="/reinspection", tags=["reinspection"])


@router.get(
    "",
    response_model=ApiResponse[list[ReinspectionRead]],
    summary="재검 큐 목록 조회",
)
async def list_queues_endpoint(
    status_: ReinspectionStatus | None = Query(
        default=None,
        alias="status",
        description="큐 상태 필터. 미지정 시 전체.",
    ),
    part_id: str | None = Query(default=None, description="부품 ID 필터."),
    skip: int = Query(default=0, ge=0, description="건너뛸 건수."),
    limit: int = Query(default=50, ge=1, le=200, description="최대 반환 건수."),
):
    docs = await list_queues(
        status=status_, part_id=part_id, skip=skip, limit=limit
    )
    return success_response(
        data=[ReinspectionRead.from_document(d).model_dump(mode="json") for d in docs]
    )


@router.get(
    "/daily-defects",
    response_model=ApiResponse[list[DailyDefectPartRead]],
    summary="당일 결함 확정 부품 목록 (part_id 기준 그룹)",
    description=(
        "재검 큐 중 `status=CLOSED` + `result.is_defect=true` 조건을 만족하는 "
        "당일 항목을 `part_id` 기준으로 모아 반환합니다. "
        "`date` 미지정 시 오늘(UTC) 기준."
    ),
)
async def list_daily_defect_parts_endpoint(
    date_str: str | None = Query(
        default=None,
        alias="date",
        description="조회 날짜 (YYYY-MM-DD, UTC). 미지정 시 오늘.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
):
    target_date: datetime | None = None
    if date_str is not None:
        try:
            from datetime import date as _date
            d = _date.fromisoformat(date_str)
            target_date = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        except ValueError:
            raise AppException(message=f"유효하지 않은 날짜입니다: {date_str}", code=400)

    groups = await list_daily_defect_parts(target_date=target_date)
    data = [
        DailyDefectPartRead(
            part_id=g["part_id"],
            total_queues=g["total_queues"],
            reasons=g["reasons"],
            latest_closed_at=g["latest_closed_at"],
            queues=[ReinspectionRead.from_document(q) for q in g["queues"]],
        ).model_dump(mode="json")
        for g in groups
    ]
    return success_response(data=data)


@router.get(
    "/{queue_id}",
    response_model=ApiResponse[ReinspectionRead],
    summary="재검 큐 단건 조회",
)
async def get_queue_endpoint(queue_id: str):
    queue = await get_queue(queue_id)
    return success_response(
        data=ReinspectionRead.from_document(queue).model_dump(mode="json")
    )


@router.post(
    "/{queue_id}/result",
    response_model=ApiResponse[ReinspectionRead],
    status_code=status.HTTP_201_CREATED,
    summary="재검 결과 등록 (작업자) → CLOSED",
)
async def submit_result_endpoint(queue_id: str, payload: ReinspectionResultCreate):
    queue = await submit_result(queue_id, payload.model_dump(mode="json"))
    return success_response(
        data=ReinspectionRead.from_document(queue).model_dump(mode="json"),
        message="Closed",
        code=201,
    )
