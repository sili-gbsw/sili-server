from datetime import datetime, timezone
from typing import Any

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import IndexModel


class ThicknessLimitRange(BaseModel):
    """두께 조합별 정상 범위 (AWS C1.1:2019 + 최원테크 연강판 SPOT 용접조건표 기준).

    이 범위의 중앙값을 MILD 기준값으로 잡고, `MaterialProfile` 의 보정 계수를
    곱한 뒤 판정 엔진이 이탈률을 계산한다.
    """

    I_min: float = Field(..., description="용접 전류 정상 하한 (kA, 1 kA = 1,000 A)")
    I_max: float = Field(..., description="용접 전류 정상 상한 (kA)")
    T_min: float = Field(
        ..., description="통전 시간 정상 하한 (cycle, 1 cycle ≈ 16.67 ms, 60 Hz 기준)"
    )
    T_max: float = Field(..., description="통전 시간 정상 상한 (cycle)")
    F_min: float = Field(
        ..., description="전극 가압력 정상 하한 (kN, 1 kN ≈ 101.97 kgf)"
    )
    F_max: float = Field(..., description="전극 가압력 정상 상한 (kN)")


class MaterialProfile(BaseModel):
    """재질별 MILD 기준값 대비 배율 (WorldAutoSteel AHSS Guidelines + SSAB Docol).

    예) DP980 은 비저항이 높아 `current_factor < 1` (전류 감소),
    `force_factor > 1` (가압력 증가) 방향으로 설정한다.
    """

    current_factor: float = Field(
        ..., description="전류 보정 배율 (MILD=1.00 기준, AHSS 는 보통 < 1)"
    )
    time_factor: float = Field(
        ..., description="통전 시간 보정 배율 (도금강/DP 계열은 보통 > 1)"
    )
    force_factor: float = Field(
        ..., description="가압력 보정 배율 (AHSS 는 +20% 이상이 표준 권고)"
    )


class QualityClassTolerance(BaseModel):
    """품질 등급(A/B/C) 별 허용 편차.

    판정 엔진은 얇은 쪽 두께가 3.2 mm 미만이면 `thin`, 이상이면 `thick`
    값을 선택하여 이탈률 정규화에 사용한다.
    값은 0~1 비율(예: 0.17 = ±17%).
    """

    thin: float = Field(
        ...,
        description="얇은 판(min(t1,t2) < 3.2 mm) 허용 편차 비율 (예: 0.17 = ±17%)",
    )
    thick: float = Field(
        ...,
        description="두꺼운 판(min(t1,t2) ≥ 3.2 mm) 허용 편차 비율",
    )


class ElectrodeShapeRule(BaseModel):
    """판두께 기준 C형/R형 전극 자동 권장 규칙.

    얇은 쪽 두께가 `thin_threshold_mm` 미만이면 `below`, 이상이면
    `above_or_equal` 형상이 권장된다. 실제 장착 전극과 권장이 다르면
    판정 엔진은 🟡 주의로 강제 격상한다.
    """

    thin_threshold_mm: float = Field(
        ..., description="C형/R형을 가르는 얇은 쪽 두께 임계 (mm)"
    )
    below: str = Field(
        ..., description="임계 미만일 때 권장 전극 형상 코드 (예: 'C-TYPE')"
    )
    above_or_equal: str = Field(
        ..., description="임계 이상일 때 권장 전극 형상 코드 (예: 'R-TYPE')"
    )


class ElectrodeWearLimit(BaseModel):
    """전극 누적 타수 기준의 마모 단계 임계.

    AWS C1.1 권고와 자동차 차체 공정 관행을 따라 1,500~2,000 타 범위에서
    주의/재검권장으로 단계 분기한다.
    """

    caution_hits: int = Field(
        ...,
        description="🟡 주의 단계 진입 누적 타수 (이 값 도달 시 마모 점수 가산 시작)",
    )
    reject_hits: int = Field(
        ...,
        description="🔴 재검권장 단계 진입 누적 타수 (전극 교체 권장 임계)",
    )


class WeldingConfig(Document):
    """시스템 동적 설정 (단일 도큐먼트 / 싱글톤).

    `config` 컬렉션에 `singleton_key == "default"` 인 1건만 존재하며,
    부팅 시 `config_seed.seed_default_config()` 가 기본값으로 시드한다.
    `PATCH /api/v1/config` 호출 시마다 version 이 +1 되고 변경 이력은
    `ConfigAudit` 에 기록된다.
    """

    singleton_key: str = Field(
        default="default",
        description="싱글톤 식별 키. unique 인덱스로 보호되어 항상 1건만 유지.",
    )
    version: int = Field(
        default=1,
        description="설정 버전. 변경이 발생한 PATCH 마다 +1 (동일 값 PATCH 는 미증가).",
    )

    thickness_limits: dict[str, ThicknessLimitRange] = Field(
        ...,
        description=(
            "두께 조합 키(`'<t1>+<t2>'`, 예: `'0.8+1.2'`) → 정상 범위. "
            "판정 엔진은 `part_master.t1+t2` 로 키를 만들어 조회한다."
        ),
    )
    material_profiles: dict[str, MaterialProfile] = Field(
        ...,
        description=(
            "재질 코드(`MILD`/`HSLA`/`DP600`/`DP980`/`UHSS`/`GA`/`GI`) → "
            "MILD 기준 보정 배율. 미등록 재질 투입 시 🔴 재검권장 강제 격상."
        ),
    )
    quality_class_tolerance: dict[str, QualityClassTolerance] = Field(
        ...,
        description=(
            "품질 등급 코드(`A`/`B`/`C`) → 허용 편차. 부품 마스터의 "
            "`quality_class` 로 조회되어 이탈률 정규화에 사용."
        ),
    )
    electrode_shape_rule: ElectrodeShapeRule = Field(
        ...,
        description="판두께 기준 C형/R형 전극 자동 권장 규칙 (불일치 시 🟡 격상).",
    )
    thickness_ratio_limit: float = Field(
        ...,
        description=(
            "이종 두께 비율 상한. `max(t1,t2)/min(t1,t2)` 가 이 값을 초과하면 "
            "🟡 주의로 강제 격상하고 '수동 파라미터 확인' 팝업을 띄운다."
        ),
    )
    electrode_wear_limit: ElectrodeWearLimit = Field(
        ..., description="전극 누적 타수 기준의 주의/재검권장 임계."
    )
    min_pitch_mm: dict[str, float] = Field(
        ...,
        description=(
            "판두께(mm, 문자열 키, 예: `'1.2'`) → 인접 타점 최소 피치(mm). "
            "좌표 데이터 수집 가능 시 활성화 (v1 보류, F-11)."
        ),
    )
    min_lap_mm: dict[str, float] = Field(
        ...,
        description=(
            "판두께(mm, 문자열 키) → 판재 겹침 최소 폭(mm). 좌표 데이터 "
            "수집 가능 시 활성화 (v1 보류, F-11)."
        ),
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="마지막 변경 시각 (UTC).",
    )

    class Settings:
        name = "config"
        indexes = [
            IndexModel("singleton_key", unique=True),
        ]


class ConfigAudit(Document):
    """`WeldingConfig` 의 모든 변경(시드/PATCH) 이력.

    PATCH 1회에서 N개 키가 바뀌면 audit 도 N건이 기록된다.
    최초 시드 시점은 `key == "__seed__"` 1건으로 별도 표시된다.
    """

    key: str = Field(
        ...,
        description=(
            "변경된 최상위 필드명 (예: `thickness_ratio_limit`). "
            "최초 시드 이벤트는 `'__seed__'`."
        ),
    )
    old_value: Any = Field(
        default=None, description="변경 전 값 (최초 시드 시 null)."
    )
    new_value: Any = Field(
        default=None, description="변경 후 값."
    )
    changed_by: str = Field(
        default="system",
        description=(
            "변경 주체. PATCH 시 `X-Changed-By` 헤더 값, 시드는 `'system'`."
        ),
    )
    changed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="변경 시각 (UTC).",
    )

    class Settings:
        name = "config_audits"
        indexes = [
            IndexModel([("changed_at", -1)]),
        ]
