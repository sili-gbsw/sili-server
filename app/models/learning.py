"""F-03. 정상 범위 자동 학습 — Beanie Document.

세션 단위로 동일 (line_id, part_id) 조합의 초기 N 타점 데이터를 수집해
전류/통전시간/가압력의 평균(μ) 과 표준편차(σ) 를 자동 산출한다 (docs F-03).

상태 전이
  COLLECTING (sample_count < target) → COMPLETE (sample_count >= target)

리셋(reset) 시 도큐먼트 자체를 삭제 — 같은 조합으로 다시 학습하려면 POST
`/learning/start` 로 새 세션을 만든다.

F-08 학습 환류 (미구현) 가 들어가면 COMPLETE 세션의 μ/σ 를 점진 갱신.
"""

from datetime import datetime, timezone
from enum import Enum

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import IndexModel


class LearningStatus(str, Enum):
    """세션 상태."""

    COLLECTING = "COLLECTING"  # 표본 수집 중 (sample_count < target)
    COMPLETE = "COMPLETE"      # 표본 도달 → μ/σ 산출 완료, params 채워짐


class LearningTrigger(str, Enum):
    """학습 이력 항목의 발생 원인 (F-08)."""

    INITIAL = "INITIAL"    # F-03 초기 100타 도달 시점의 산출
    FEEDBACK = "FEEDBACK"  # F-08 재검 결과 '실제 정상' 환류로 갱신


class ParamStats(BaseModel):
    """파라미터별 평균/표준편차/샘플 수."""

    mean: float = Field(..., description="평균 (μ).")
    std: float = Field(..., ge=0, description="표본 표준편차 (σ, n-1 분모).")
    sample_count: int = Field(..., ge=2, description="통계 산출에 사용된 표본 수.")


class LearningParams(BaseModel):
    """학습된 정상 범위 파라미터.

    COLLECTING 상태에서는 부모 도큐먼트의 `params` 가 None — target 도달
    시점에 한 번에 채워진다.
    """

    current_kA: ParamStats
    weld_time_cycle: ParamStats
    force_kN: ParamStats


class LearningHistoryEntry(BaseModel):
    """학습 이력 1건 (F-08). 세션의 `history` 배열에 append-only."""

    timestamp: datetime = Field(
        ..., description="이 이력 항목이 기록된 시각 (UTC)."
    )
    trigger: LearningTrigger = Field(
        ..., description="발생 원인 (INITIAL: 초기 완료, FEEDBACK: 환류)."
    )
    source_queue_id: str | None = Field(
        default=None,
        description="FEEDBACK 의 원천 재검 큐 ID. INITIAL 은 null.",
    )
    source_event_ids: list[str] = Field(
        default_factory=list,
        description=(
            "이 시점에 새로 추가된 표본 이벤트들. INITIAL 은 빈 배열 "
            "(초기 window 전체이므로 ID 나열 생략)."
        ),
    )
    sample_count: int = Field(
        ..., ge=2, description="이 산출에 사용된 전체 표본 수."
    )
    params: LearningParams = Field(
        ..., description="이 시점에 산출된 μ/σ 스냅샷."
    )


class NormalRangeLearning(Document):
    """정상 범위 학습 세션 (`normal_range_learning` 컬렉션).

    `(line_id, part_id)` 가 도메인 키이며 unique 인덱스로 보호된다. 같은
    조합으로 동시에 여러 세션을 굴리는 것은 의미가 없기 때문.
    """

    line_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="생산 라인 식별자.",
    )
    part_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="부품 마스터 식별자.",
    )

    status: LearningStatus = Field(
        default=LearningStatus.COLLECTING,
        description="현재 세션 상태.",
    )
    target_sample_count: int = Field(
        default=100,
        ge=2,
        description="목표 표본 수. 기본 100 (docs F-03). n=1 은 σ 산출 불가.",
    )
    sample_count: int = Field(
        default=0,
        ge=0,
        description="ingest 후크가 누적하는 현재 표본 수.",
    )

    sample_window_start: datetime = Field(
        ...,
        description=(
            "세션 시작 시각 (UTC). 이 시각 이후 `WeldEvent.timestamp` 만 "
            "통계 표본에 포함된다 — 과거 이벤트가 새 세션에 새지 않도록 보호."
        ),
    )

    params: LearningParams | None = Field(
        default=None,
        description="COMPLETE 시점에 산출된 정상 범위 (μ/σ).",
    )

    feedback_event_ids: list[str] = Field(
        default_factory=list,
        description=(
            "F-08 환류로 표본에 추가된 event_id 목록. 재검 결과가 '실제 "
            "정상' 으로 등록된 이벤트들이 모인다. 중복 적용은 차단됨."
        ),
    )
    history: list[LearningHistoryEntry] = Field(
        default_factory=list,
        description=(
            "μ/σ 변경 이력. INITIAL 1건 + FEEDBACK N건이 시간순으로 쌓인다."
        ),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: datetime | None = Field(
        default=None,
        description="COMPLETE 전이 시각 (UTC).",
    )

    class Settings:
        name = "normal_range_learning"
        indexes = [
            IndexModel(
                [("line_id", 1), ("part_id", 1)],
                unique=True,
                name="line_part_unique",
            ),
        ]
