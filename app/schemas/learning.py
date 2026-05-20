"""F-03. 정상 범위 자동 학습 — Pydantic DTO."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.learning import (
    LearningHistoryEntry,
    LearningParams,
    LearningStatus,
    NormalRangeLearning,
)


class LearningStartRequest(BaseModel):
    """`POST /api/v1/learning/start` 요청 본문."""

    line_id: str = Field(
        ..., min_length=1, max_length=64, examples=["LINE-A"]
    )
    part_id: str = Field(
        ..., min_length=1, max_length=64, examples=["BODY-0042"]
    )
    target_sample_count: int = Field(
        default=100,
        ge=2,
        le=10000,
        description="목표 표본 수. 기본 100, 최소 2 (σ 산출 가능 최소).",
        examples=[100],
    )


class LearningResetRequest(BaseModel):
    """`POST /api/v1/learning/reset` 요청 본문."""

    line_id: str = Field(..., min_length=1, max_length=64, examples=["LINE-A"])
    part_id: str | None = Field(
        default=None,
        max_length=64,
        description="생략 시 해당 라인의 모든 세션을 삭제.",
        examples=["BODY-0042"],
    )


class LearningSeedRequest(BaseModel):
    """`POST /api/v1/learning/seed` 요청 본문 (개발/테스트용)."""

    line_id: str = Field(..., min_length=1, max_length=64, examples=["LINE-A"])
    part_id: str = Field(..., min_length=1, max_length=64, examples=["BODY-0042"])


class LearningRead(BaseModel):
    """`GET /api/v1/learning/{line_id}` 응답 항목."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    line_id: str
    part_id: str
    status: LearningStatus
    target_sample_count: int
    sample_count: int
    sample_window_start: datetime
    params: LearningParams | None
    feedback_event_ids: list[str]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_document(cls, doc: NormalRangeLearning) -> "LearningRead":
        return cls(
            id=str(doc.id),
            line_id=doc.line_id,
            part_id=doc.part_id,
            status=doc.status,
            target_sample_count=doc.target_sample_count,
            sample_count=doc.sample_count,
            sample_window_start=doc.sample_window_start,
            params=doc.params,
            feedback_event_ids=list(doc.feedback_event_ids),
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            completed_at=doc.completed_at,
        )


class LearningHistoryRead(BaseModel):
    """`GET /api/v1/learning/{line_id}/history` 응답 항목.

    세션별 history 를 flatten 하여 라인 단위 시간순 이력으로 노출.
    """

    line_id: str
    part_id: str
    history: list[LearningHistoryEntry] = Field(default_factory=list)
