"""F-01. 공정 데이터 수집(Ingestion) — Beanie Document + 임베드 모델.

PLC 게이트웨이가 타점 완료 시점에 `POST /api/v1/weld-events` 로 보낸
측정값을 시계열로 저장한다. 판정 결과(`judgement`) 는 임베드되며,
F-04 (강제 격상) + F-05 (점수 산출) 구현 전까지는 `None` 으로 둔다.

저장 시 부품 마스터(`Part`) 의 일부 필드(`t1/t2/material_code/electrode_shape`)
는 **이벤트 스냅샷**으로 함께 기록되어, 추후 마스터가 변경되어도 그 시점의
공정 조건을 그대로 추적할 수 있도록 한다 (NFR: 영구 로그·추적성).
"""

from datetime import datetime, timezone
from enum import Enum

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import IndexModel

from app.models.part import ElectrodeShape, MaterialCode


class JudgementStatus(str, Enum):
    """판정 결과 상태. 점수 구간은 docs 7.2 / 10.3 절 참고."""

    NORMAL = "NORMAL"    # 🟢 0~30
    CAUTION = "CAUTION"  # 🟡 31~60
    REJECT = "REJECT"    # 🔴 61~100


class JudgementDeviation(BaseModel):
    """파라미터별 이탈률/점수 (F-05 가 채움). 단위는 정규화 % 또는 0~100 점수."""

    current: float = Field(default=0.0, description="용접 전류 이탈률 (정규화 %).")
    weld_time: float = Field(default=0.0, description="통전 시간 이탈률 (정규화 %).")
    force: float = Field(default=0.0, description="가압력 이탈률 (정규화 %).")
    wear: float = Field(default=0.0, description="전극 마모 점수 (0~100).")


class Judgement(BaseModel):
    """타점 이벤트의 판정 결과 (WeldEvent 에 임베드).

    F-01 단계에서는 생성되지 않으며 (`WeldEvent.judgement is None`),
    F-04 + F-05 구현 후 ingestion 흐름이 자동으로 채워 넣는다.
    """

    score: float = Field(
        ..., ge=0, le=100, description="이상 점수 (0~100, 높을수록 비정상)."
    )
    status: JudgementStatus = Field(..., description="점수 구간에 따른 상태 분기.")
    forced_reason: str | None = Field(
        default=None,
        description=(
            "F-04 강제 격상 사유 코드 (예: 'MATERIAL_MISMATCH', "
            "'THICKNESS_RATIO_OVER', 'ELECTRODE_SHAPE_MISMATCH'). 강제 격상이 "
            "아니면 null."
        ),
    )
    deviations: JudgementDeviation = Field(
        default_factory=JudgementDeviation,
        description="가중합 계산에 들어간 항목별 기여도.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="판정이 산출된 시각 (UTC).",
    )


class WeldEvent(Document):
    """타점 이벤트 도큐먼트 (`weld_events` 컬렉션).

    `event_id` 는 도메인 식별자(unique). `_id` 는 ObjectId 기본값.
    시계열 조회 최적화를 위해 `(part_id, timestamp desc)` 와 `(timestamp desc)`
    복합 인덱스를 둔다.
    """

    event_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="이벤트 식별자 (예: 'evt_<hex>'). 서버에서 발급, unique.",
    )
    part_id: str = Field(
        ..., description="부품 마스터 식별자. `Part.part_id` 와 일치해야 한다."
    )
    point_id: str = Field(
        ..., description="부품 내 타점 식별자 (예: 'P-014')."
    )

    current_kA: float = Field(..., gt=0, description="측정 용접 전류 (kA).")
    weld_time_cycle: float = Field(
        ..., gt=0, description="측정 통전 시간 (cycle, 1 cycle ≈ 16.67 ms)."
    )
    force_kN: float = Field(..., gt=0, description="측정 전극 가압력 (kN).")
    cumulative_hits: int = Field(
        ..., ge=0, description="이 타점 시점의 전극 누적 타수."
    )

    t1: float = Field(..., gt=0, description="판재 1 두께 (mm) — 이벤트 스냅샷.")
    t2: float = Field(..., gt=0, description="판재 2 두께 (mm) — 이벤트 스냅샷.")
    material_code: MaterialCode = Field(
        ..., description="실측 재질 코드 — 이벤트 스냅샷. 부품 마스터와 다르면 강제 격상 대상 (F-04)."
    )
    electrode_shape: ElectrodeShape = Field(
        ..., description="장착 전극 형상 코드 — 이벤트 스냅샷."
    )

    judgement: Judgement | None = Field(
        default=None,
        description=(
            "판정 결과 (F-04/F-05). Phase 1 시점에는 null (판정 대기). "
            "Phase 2 구현 후 자동 채움."
        ),
    )

    timestamp: datetime = Field(
        ...,
        description="PLC 송신 타임스탬프 (UTC 권장). NFR: 시간 동기는 NTP, PLC 송신값 우선.",
    )

    class Settings:
        name = "weld_events"
        indexes = [
            IndexModel("event_id", unique=True),
            IndexModel([("part_id", 1), ("timestamp", -1)]),
            IndexModel([("timestamp", -1)]),
        ]
