"""F-10. 설정(Config) 관리 — Pydantic DTO."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.welding_config import (
    ElectrodeShapeRule,
    ElectrodeWearLimit,
    MaterialProfile,
    QualityClassTolerance,
    ThicknessLimitRange,
)


class ConfigRead(BaseModel):
    """`GET /api/v1/config` 응답 본문.

    `WeldingConfig` 도큐먼트에서 운영에 필요한 필드만 노출하며,
    내부 식별자(`_id`, `singleton_key`)는 응답에 포함하지 않는다.
    """

    model_config = ConfigDict(from_attributes=True)

    version: int = Field(
        ..., description="설정 버전 (변경 시 +1, 시드 직후 값은 1)."
    )
    thickness_limits: dict[str, ThicknessLimitRange] = Field(
        ...,
        description=(
            "두께 조합 키(`'<t1>+<t2>'` 형식, 예: `'0.8+1.2'`) → 정상 범위. "
            "판정 엔진이 부품 마스터의 두께로 키를 만들어 조회한다."
        ),
    )
    material_profiles: dict[str, MaterialProfile] = Field(
        ...,
        description=(
            "재질 코드(`MILD`/`HSLA`/`DP600`/`DP980`/`UHSS`/`GA`/`GI`) → "
            "MILD 기준 보정 배율."
        ),
    )
    quality_class_tolerance: dict[str, QualityClassTolerance] = Field(
        ...,
        description="품질 등급 코드(`A`/`B`/`C`) → 허용 편차 (얇은/두꺼운 판 별).",
    )
    electrode_shape_rule: ElectrodeShapeRule = Field(
        ..., description="판두께 기준 C형/R형 전극 자동 권장 규칙."
    )
    thickness_ratio_limit: float = Field(
        ...,
        description=(
            "이종 두께 비율 상한. `max(t1,t2)/min(t1,t2)` 가 이 값을 초과하면 "
            "🟡 주의로 강제 격상."
        ),
    )
    electrode_wear_limit: ElectrodeWearLimit = Field(
        ..., description="전극 누적 타수 기준의 주의/재검권장 임계."
    )
    min_pitch_mm: dict[str, float] = Field(
        ...,
        description=(
            "판두께(mm, 문자열 키) → 인접 타점 최소 피치(mm). "
            "v1 보류 항목 (F-11, 좌표 데이터 수집 시 활성화)."
        ),
    )
    min_lap_mm: dict[str, float] = Field(
        ...,
        description=(
            "판두께(mm, 문자열 키) → 판재 겹침 최소 폭(mm). "
            "v1 보류 항목 (F-11)."
        ),
    )
    updated_at: datetime = Field(..., description="마지막 변경 시각 (UTC).")

    @classmethod
    def from_document(cls, doc) -> "ConfigRead":
        return cls(
            version=doc.version,
            thickness_limits=doc.thickness_limits,
            material_profiles=doc.material_profiles,
            quality_class_tolerance=doc.quality_class_tolerance,
            electrode_shape_rule=doc.electrode_shape_rule,
            thickness_ratio_limit=doc.thickness_ratio_limit,
            electrode_wear_limit=doc.electrode_wear_limit,
            min_pitch_mm=doc.min_pitch_mm,
            min_lap_mm=doc.min_lap_mm,
            updated_at=doc.updated_at,
        )


class ConfigUpdate(BaseModel):
    """`PATCH /api/v1/config` 요청 본문.

    모든 필드가 선택값(`null` 허용). 제공된 키만 갱신되며, 동일 값이면
    audit 도 만들지 않고 version 도 그대로 유지한다.
    `dict` 필드는 **전체 교체** 방식이므로 부분 갱신 시 기존 항목까지
    모두 포함해서 보내야 한다 (예: 두께 조합 1개 추가 시 기존 7개 + 새 1개).
    """

    thickness_limits: dict[str, ThicknessLimitRange] | None = Field(
        default=None,
        description=(
            "두께 조합 키 → 정상 범위 전체 교체. 키 형식: `'<t1>+<t2>'` "
            "(예: `'0.8+1.2'`)."
        ),
    )
    material_profiles: dict[str, MaterialProfile] | None = Field(
        default=None,
        description=(
            "재질 코드 → MILD 기준 보정 배율 전체 교체. "
            "키 예: `MILD`, `HSLA`, `DP600`, `DP980`, `UHSS`, `GA`, `GI`."
        ),
    )
    quality_class_tolerance: dict[str, QualityClassTolerance] | None = Field(
        default=None,
        description="품질 등급 코드(`A`/`B`/`C`) → 허용 편차 전체 교체.",
    )
    electrode_shape_rule: ElectrodeShapeRule | None = Field(
        default=None,
        description="C형/R형 전극 자동 권장 규칙 (임계 두께·형상 코드).",
    )
    thickness_ratio_limit: float | None = Field(
        default=None,
        gt=0,
        description="이종 두께 비율 상한 (`> 0`). 일반적으로 3.0 안팎.",
    )
    electrode_wear_limit: ElectrodeWearLimit | None = Field(
        default=None,
        description="전극 누적 타수 기준의 주의/재검권장 임계.",
    )
    min_pitch_mm: dict[str, float] | None = Field(
        default=None,
        description="판두께(mm, 문자열 키) → 최소 피치(mm) 전체 교체. (F-11)",
    )
    min_lap_mm: dict[str, float] | None = Field(
        default=None,
        description="판두께(mm, 문자열 키) → 최소 Lap(mm) 전체 교체. (F-11)",
    )


class ConfigAuditRead(BaseModel):
    """`GET /api/v1/config/audit` 응답 본문 (배열 요소).

    한 PATCH 호출이 N개의 필드를 바꾸면 N건의 audit 가 만들어진다.
    최초 시드 시점은 `key == '__seed__'` 1건으로 식별된다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="ConfigAudit 도큐먼트의 ObjectId(문자열).")
    key: str = Field(
        ...,
        description=(
            "변경된 최상위 필드명. 최초 시드 이벤트는 `'__seed__'`."
        ),
    )
    old_value: Any = Field(
        default=None, description="변경 전 값 (최초 시드 시 null)."
    )
    new_value: Any = Field(default=None, description="변경 후 값.")
    changed_by: str = Field(
        ..., description="변경 주체 (PATCH 의 `X-Changed-By` 헤더 또는 `'system'`)."
    )
    changed_at: datetime = Field(..., description="변경 시각 (UTC).")

    @classmethod
    def from_document(cls, doc) -> "ConfigAuditRead":
        return cls(
            id=str(doc.id),
            key=doc.key,
            old_value=doc.old_value,
            new_value=doc.new_value,
            changed_by=doc.changed_by,
            changed_at=doc.changed_at,
        )
