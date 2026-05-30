"""F-06. 재검 큐 관리 — Pydantic DTO."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.reinspection import (
    ReinspectionReason,
    ReinspectionResult,
    ReinspectionStatus,
)



class ReinspectionResultCreate(BaseModel):
    """`POST /api/v1/reinspection/{queue_id}/result` 요청 본문."""

    is_defect: bool = Field(
        ..., description="실제 불량 여부.", examples=[True]
    )
    inspector_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="검사자 식별자.",
        examples=["WORKER-007"],
    )
    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="검사 메모.",
        examples=["가압력 부족 — 너깃 직경 3.8 mm"],
    )


class ReinspectionRead(BaseModel):
    """`GET /api/v1/reinspection(/{queue_id})` 응답 본문."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="MongoDB ObjectId(문자열).")
    queue_id: str
    part_id: str
    event_ids: list[str]
    status: ReinspectionStatus
    reason: ReinspectionReason
    result: ReinspectionResult | None
    created_at: datetime
    closed_at: datetime | None

    @classmethod
    def from_document(cls, doc) -> "ReinspectionRead":
        return cls(
            id=str(doc.id),
            queue_id=doc.queue_id,
            part_id=doc.part_id,
            event_ids=list(doc.event_ids),
            status=doc.status,
            reason=doc.reason,
            result=doc.result,
            created_at=doc.created_at,
            closed_at=doc.closed_at,
        )


class DailyDefectPartRead(BaseModel):
    """`GET /api/v1/reinspection/daily-defects` 응답 항목 — part_id 기준 그룹."""

    part_id: str = Field(..., description="부품 마스터 식별자.")
    total_queues: int = Field(..., description="당일 결함 확정 큐 건수.")
    reasons: list[ReinspectionReason] = Field(
        ..., description="해당 부품에서 발생한 고유 사유 목록."
    )
    latest_closed_at: datetime = Field(..., description="가장 최근 결함 확정 시각 (UTC).")
    queues: list[ReinspectionRead] = Field(..., description="결함 확정 큐 상세 목록.")
