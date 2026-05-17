"""F-01. 공정 데이터 수집 — Pydantic DTO."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.part import ElectrodeShape, MaterialCode
from app.models.weld_event import Judgement


class WeldEventCreate(BaseModel):
    """`POST /api/v1/weld-events` 요청 본문.

    PLC 게이트웨이가 타점 완료 직후 전송한다. `event_id` 는 서버에서 발급하므로
    요청에 포함하지 않는다.
    """

    line_id: str = Field(
        default="LINE-DEFAULT",
        min_length=1,
        max_length=64,
        description=(
            "생산 라인 식별자. F-03 학습 집계 키. 생략 시 'LINE-DEFAULT'."
        ),
        examples=["LINE-A"],
    )
    part_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="부품 마스터 식별자. 미등록 시 404 반환.",
        examples=["BODY-0042"],
    )
    point_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="부품 내 타점 식별자.",
        examples=["P-014"],
    )
    current_kA: float = Field(
        ..., gt=0, description="측정 용접 전류 (kA).", examples=[9.5]
    )
    weld_time_cycle: float = Field(
        ..., gt=0, description="측정 통전 시간 (cycle).", examples=[12]
    )
    force_kN: float = Field(
        ..., gt=0, description="측정 전극 가압력 (kN).", examples=[2.6]
    )
    cumulative_hits: int = Field(
        ..., ge=0, description="전극 누적 타수.", examples=[1240]
    )
    t1: float = Field(..., gt=0, description="판재 1 두께 (mm).", examples=[0.8])
    t2: float = Field(..., gt=0, description="판재 2 두께 (mm).", examples=[1.2])
    material_code: MaterialCode = Field(
        ..., description="실측 재질 코드.", examples=["MILD"]
    )
    electrode_shape: ElectrodeShape = Field(
        ..., description="장착 전극 형상 코드.", examples=["C-TYPE"]
    )
    timestamp: datetime = Field(
        ...,
        description="PLC 송신 시각 (ISO 8601, UTC 권장).",
        examples=["2026-05-16T14:25:33.412Z"],
    )


class WeldEventRead(BaseModel):
    """`POST /api/v1/weld-events` 응답 본문."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="MongoDB ObjectId(문자열).")
    event_id: str = Field(..., description="서버 발급 이벤트 식별자.")
    line_id: str
    part_id: str
    point_id: str
    current_kA: float
    weld_time_cycle: float
    force_kN: float
    cumulative_hits: int
    t1: float
    t2: float
    material_code: MaterialCode
    electrode_shape: ElectrodeShape
    judgement: Judgement | None = Field(
        default=None,
        description="판정 결과. Phase 2 (F-04/F-05) 미구현 단계에서는 null.",
    )
    timestamp: datetime

    @classmethod
    def from_document(cls, doc) -> "WeldEventRead":
        return cls(
            id=str(doc.id),
            event_id=doc.event_id,
            line_id=doc.line_id,
            part_id=doc.part_id,
            point_id=doc.point_id,
            current_kA=doc.current_kA,
            weld_time_cycle=doc.weld_time_cycle,
            force_kN=doc.force_kN,
            cumulative_hits=doc.cumulative_hits,
            t1=doc.t1,
            t2=doc.t2,
            material_code=doc.material_code,
            electrode_shape=doc.electrode_shape,
            judgement=doc.judgement,
            timestamp=doc.timestamp,
        )
