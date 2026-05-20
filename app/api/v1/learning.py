"""F-03 정상 범위 자동 학습 + F-08 학습 환류 — REST 엔드포인트.

- POST /api/v1/learning/start          : 신규 세션 시작 (Admin)
- GET  /api/v1/learning/{line_id}      : 라인별 세션 조회 (QA)
- GET  /api/v1/learning/{line_id}/history : F-08 학습 이력 조회 (QA)
- POST /api/v1/learning/reset          : 세션 초기화 (Admin)
"""

from fastapi import APIRouter, Depends, Query, status

from app.core.response import ApiResponse, success_response
from app.models.user import User, UserRole
from app.services.auth import require_role
from app.schemas.learning import (
    LearningHistoryRead,
    LearningRead,
    LearningResetRequest,
    LearningSeedRequest,
    LearningStartRequest,
)
from app.services.learning_service import (
    get_learning_history,
    get_recent_samples,
    list_learning_sessions,
    reset_learning,
    seed_learning_history,
    start_learning,
)

router = APIRouter(prefix="/learning", tags=["learning"])


@router.post(
    "/start",
    response_model=ApiResponse[LearningRead],
    status_code=status.HTTP_201_CREATED,
    summary="정상 범위 학습 시작 (Admin)",
)
async def start_learning_endpoint(payload: LearningStartRequest):
    session = await start_learning(
        line_id=payload.line_id,
        part_id=payload.part_id,
        target_sample_count=payload.target_sample_count,
    )
    return success_response(
        data=LearningRead.from_document(session).model_dump(mode="json"),
        message="Started",
        code=201,
    )


@router.get(
    "/{line_id}",
    response_model=ApiResponse[list[LearningRead]],
    summary="라인별 학습 세션 조회",
)
async def list_learning_endpoint(
    line_id: str,
    part_id: str | None = Query(default=None, description="부품 ID 필터."),
):
    sessions = await list_learning_sessions(line_id=line_id, part_id=part_id)
    return success_response(
        data=[
            LearningRead.from_document(s).model_dump(mode="json")
            for s in sessions
        ]
    )


@router.get(
    "/{line_id}/history",
    response_model=ApiResponse[list[LearningHistoryRead]],
    summary="라인별 학습 이력 조회 (F-08)",
)
async def get_learning_history_endpoint(
    line_id: str,
    part_id: str | None = Query(default=None, description="부품 ID 필터."),
):
    rows = await get_learning_history(line_id=line_id, part_id=part_id)
    return success_response(data=rows)


@router.get(
    "/{line_id}/samples",
    response_model=ApiResponse[list[dict]],
    summary="라인별 최근 N개 타점 표본 (per-sample 추세용)",
)
async def get_recent_samples_endpoint(
    line_id: str,
    part_id: str | None = Query(default=None, description="부품 ID 필터."),
    last: int = Query(
        default=10,
        ge=1,
        le=200,
        description="최대 표본 수 (기본 10, 최대 200).",
    ),
):
    rows = await get_recent_samples(
        line_id=line_id, part_id=part_id, last=last
    )
    return success_response(data=rows)


@router.post(
    "/reset",
    response_model=ApiResponse[dict],
    summary="학습 세션 초기화 (Admin)",
)
async def reset_learning_endpoint(payload: LearningResetRequest):
    deleted = await reset_learning(
        line_id=payload.line_id, part_id=payload.part_id
    )
    return success_response(
        data={"deleted_count": deleted},
        message="Reset",
    )


@router.post(
    "/seed",
    response_model=ApiResponse[LearningRead],
    status_code=status.HTTP_201_CREATED,
    summary="학습 이력 테스트 데이터 주입 (개발/테스트용)",
)
async def seed_learning_endpoint(
    payload: LearningSeedRequest,
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    """INITIAL 1건 + FEEDBACK 2건 이력을 가진 COMPLETE 세션을 생성.

    이미 세션이 존재하면 덮어쓰지 않고 기존 세션을 반환.
    히스토그램·추세 그래프 개발 시 사용.
    """
    session = await seed_learning_history(
        line_id=payload.line_id, part_id=payload.part_id
    )
    return success_response(
        data=LearningRead.from_document(session).model_dump(mode="json"),
        message="Seeded",
        code=201,
    )
