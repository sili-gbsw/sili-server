"""F-04 (강제 격상) + F-05 (판정 엔진).

판정 엔진 진입부에서 docs 4절 표의 4개 강제 격상 룰을 순차 검사한다.
어떤 룰에 매치되면 F-05 점수 산출을 건너뛰고 즉시 `Judgement` 를 반환.
어떤 룰에도 안 걸리면 F-05 로 진입 (현재는 placeholder, Phase 2 후속).

F-04 룰 우선순위
  1. (REJECT) 미등록 재질 — config.material_profiles 에 없는 코드.
  2. (CAUTION) 재질 불일치 — 부품 마스터 등록 vs 실측 코드 차이.
  3. (CAUTION) 두께 비 한계 초과 — max(t1,t2)/min(t1,t2) > config.thickness_ratio_limit.
  4. (CAUTION) 전극 형상 불일치 — t_thin 기준 권장 형상 vs 실측 형상 차이.

첫 매치에서 즉시 반환한다 (의사코드의 force_caution 호출 흐름과 일치).
"""

from app.models.part import Part
from app.models.weld_event import (
    ForcedReason,
    Judgement,
    JudgementDeviation,
    JudgementStatus,
    WeldEvent,
)
from app.models.welding_config import WeldingConfig

# 강제 격상 시 점수. F-05 미진입이라 정확한 점수는 없지만, 상태 구간
# 진입점(또는 최대값)으로 일관 설정하여 점수 기반 통계/필터링이 깨지지 않게 한다.
_CAUTION_FORCED_SCORE = 31.0
_REJECT_FORCED_SCORE = 100.0


def check_forced_escalation(
    event: WeldEvent,
    part: Part,
    config: WeldingConfig,
) -> Judgement | None:
    """F-04 강제 격상 사전 체크. 첫 매치 Judgement 반환, 무매치는 None."""
    # 1. 미등록 재질 → REJECT
    if event.material_code.value not in config.material_profiles:
        return _build_forced(
            score=_REJECT_FORCED_SCORE,
            status=JudgementStatus.REJECT,
            reason=ForcedReason.MATERIAL_UNREGISTERED,
        )

    # 2. 재질 불일치 (등록 vs 실측) → CAUTION
    if event.material_code != part.material_code:
        return _build_forced(
            score=_CAUTION_FORCED_SCORE,
            status=JudgementStatus.CAUTION,
            reason=ForcedReason.MATERIAL_MISMATCH,
        )

    # 3. 두께 비 초과 → CAUTION
    t_thin = min(event.t1, event.t2)
    t_thick = max(event.t1, event.t2)
    if t_thin > 0 and t_thick / t_thin > config.thickness_ratio_limit:
        return _build_forced(
            score=_CAUTION_FORCED_SCORE,
            status=JudgementStatus.CAUTION,
            reason=ForcedReason.THICKNESS_RATIO_OVER,
        )

    # 4. 전극 형상 불일치 → CAUTION
    rule = config.electrode_shape_rule
    expected_shape = rule.below if t_thin < rule.thin_threshold_mm else rule.above_or_equal
    if event.electrode_shape.value != expected_shape:
        return _build_forced(
            score=_CAUTION_FORCED_SCORE,
            status=JudgementStatus.CAUTION,
            reason=ForcedReason.ELECTRODE_SHAPE_MISMATCH,
        )

    return None


def _build_forced(
    *,
    score: float,
    status: JudgementStatus,
    reason: ForcedReason,
) -> Judgement:
    return Judgement(
        score=score,
        status=status,
        forced_reason=reason,
        deviations=JudgementDeviation(),
    )


async def evaluate(
    event: WeldEvent,
    part: Part,
    config: WeldingConfig,
) -> Judgement | None:
    """타점 이벤트 평가 엔진.

    1) F-04 강제 격상 사전 체크 — 매치 시 즉시 반환.
    2) F-05 점수 산출 — Phase 2 후속 (현재 placeholder, None 반환).
    """
    forced = check_forced_escalation(event, part, config)
    if forced is not None:
        return forced

    # F-05 점수 산출 자리 (Phase 2 에서 채움).
    return None
