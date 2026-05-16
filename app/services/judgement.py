"""F-04 (강제 격상) + F-05 (판정 엔진).

판정 엔진 진입부에서 docs 4절 표의 4개 강제 격상 룰을 순차 검사한다.
어떤 룰에 매치되면 F-05 점수 산출을 건너뛰고 즉시 `Judgement` 를 반환.
어떤 룰에도 안 걸리면 F-05 점수 산출로 진입한다 (가중합 → 상태 분기).

F-04 룰 우선순위
  1. (REJECT) 미등록 재질 — config.material_profiles 에 없는 코드.
  2. (CAUTION) 재질 불일치 — 부품 마스터 등록 vs 실측 코드 차이.
  3. (CAUTION) 두께 비 한계 초과 — max(t1,t2)/min(t1,t2) > config.thickness_ratio_limit.
  4. (CAUTION) 전극 형상 불일치 — t_thin 기준 권장 형상 vs 실측 형상 차이.

F-05 점수 모델 (docs 10절 의사코드)
  score = dev(current) * 0.30
        + dev(weld_time) * 0.20
        + dev(force)    * 0.20
        + wear_score(hits)            * 0.15
        + thickness_dev_score(t)      * 0.10
        + material_mismatch_score()   * 0.05
  → 0~100 clamp → 상태 분기 (NORMAL ≤30 / CAUTION ≤60 / REJECT 그 외)
"""

from app.models.part import Part
from app.models.weld_event import (
    ForcedReason,
    Judgement,
    JudgementDeviation,
    JudgementStatus,
    WeldEvent,
)
from app.models.welding_config import ElectrodeWearLimit, WeldingConfig

# === F-04 강제 격상 상수 ===
_CAUTION_FORCED_SCORE = 31.0
_REJECT_FORCED_SCORE = 100.0

# === F-05 가중치 (docs 5.2 / 10.2 절) ===
_WEIGHT_CURRENT = 0.30
_WEIGHT_TIME = 0.20
_WEIGHT_FORCE = 0.20
_WEIGHT_WEAR = 0.15
_WEIGHT_THICKNESS = 0.10
_WEIGHT_MATERIAL = 0.05

# === F-05 상태 분기 임계 (docs 10.3) ===
_STATUS_NORMAL_MAX = 30.0
_STATUS_CAUTION_MAX = 60.0

# 두께 변화 1단위(5%) 당 점수.
_THICKNESS_DEV_UNIT_PCT = 0.05


# --------------------------------------------------------------------------- #
# F-04 강제 격상 사전 체크
# --------------------------------------------------------------------------- #


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
    expected_shape = (
        rule.below if t_thin < rule.thin_threshold_mm else rule.above_or_equal
    )
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


# --------------------------------------------------------------------------- #
# F-05 점수 산출
# --------------------------------------------------------------------------- #


def compute_score(
    event: WeldEvent,
    part: Part,
    config: WeldingConfig,
) -> tuple[float, JudgementDeviation]:
    """이상 점수(0~100)와 항목별 이탈률을 반환.

    부품 마스터에 등록된 두께 조합 키로 config 의 정상 범위를 조회한다.
    조합 키가 config 에 없으면 점수 산출이 불가하므로 (0, 빈 deviation)
    을 돌려 호출자가 판정을 정상으로 두지 않도록 한다(추후 보강 가능).
    """
    deviations = JudgementDeviation()

    # 1) 두께 조합 키 = 부품 마스터 등록값.
    combo = _thickness_combo_key(part.t1, part.t2)
    limits = config.thickness_limits.get(combo)
    if limits is None:
        return 0.0, deviations

    # 2) 등급별 허용 편차 — 얇은 쪽 두께가 임계(thin_threshold_mm) 미만이면 thin, 이상이면 thick.
    tol_box = config.quality_class_tolerance.get(part.quality_class.value)
    if tol_box is None:
        return 0.0, deviations
    t_thin = min(part.t1, part.t2)
    threshold = config.electrode_shape_rule.thin_threshold_mm
    tolerance = tol_box.thin if t_thin < threshold else tol_box.thick

    # 3) MILD 기준 중앙값 × 재질 보정.
    profile = config.material_profiles.get(event.material_code.value)
    if profile is None:
        return 0.0, deviations

    i_center = (limits.I_min + limits.I_max) / 2 * profile.current_factor
    t_center = (limits.T_min + limits.T_max) / 2 * profile.time_factor
    f_center = (limits.F_min + limits.F_max) / 2 * profile.force_factor

    # 4) 항목별 이탈률.
    dev_current = _normalized_dev(event.current_kA, i_center, tolerance)
    dev_time = _normalized_dev(event.weld_time_cycle, t_center, tolerance)
    dev_force = _normalized_dev(event.force_kN, f_center, tolerance)
    wear_pts = _wear_score(event.cumulative_hits, config.electrode_wear_limit)
    thickness_pts = _thickness_dev_score(
        event.t1, event.t2, part.t1, part.t2
    )
    # 재질 불일치는 F-04 에서 이미 강제 격상으로 빠지므로 여기 진입 시 항상 0.
    material_pts = 0.0

    # 5) 가중합 → 0~100 clamp.
    raw = (
        dev_current * _WEIGHT_CURRENT
        + dev_time * _WEIGHT_TIME
        + dev_force * _WEIGHT_FORCE
        + wear_pts * _WEIGHT_WEAR
        + thickness_pts * _WEIGHT_THICKNESS
        + material_pts * _WEIGHT_MATERIAL
    )
    score = max(0.0, min(100.0, raw))

    deviations = JudgementDeviation(
        current=dev_current,
        weld_time=dev_time,
        force=dev_force,
        wear=wear_pts,
    )
    return score, deviations


def _thickness_combo_key(t1: float, t2: float) -> str:
    """`config.thickness_limits` 키 형식 (예: '0.8+1.2')."""
    return f"{t1}+{t2}"


def _normalized_dev(measured: float, center: float, tolerance: float) -> float:
    """의사코드 dev() — 중앙값 대비 이탈률(%) 을 허용 편차로 정규화.

    `tolerance` 는 0~1 비율(예: 0.17 = ±17%). 반환값은 정규화된 점수로
    100 을 넘을 수 있다 (가중치 적용 후 최종 score 에서 0~100 clamp).
    """
    if center <= 0 or tolerance <= 0:
        return 0.0
    raw_pct = abs(measured - center) / center * 100
    return raw_pct / (tolerance * 100) * 100


def _wear_score(hits: int, limit: ElectrodeWearLimit) -> float:
    """전극 누적 타수 점수.

    - hits ≤ caution: 0 (정상)
    - caution < hits ≤ reject: 선형 0 → 100
    - hits > reject: 100 + 한계 초과분(span 비례) 가산. cap 없음 (clamp 는 최종 score 에서).
    """
    if hits <= limit.caution_hits:
        return 0.0
    span = max(1, limit.reject_hits - limit.caution_hits)
    if hits <= limit.reject_hits:
        return (hits - limit.caution_hits) / span * 100
    overflow = (hits - limit.reject_hits) / span
    return 100.0 + overflow * 100


def _thickness_dev_score(
    t1_event: float, t2_event: float, t1_master: float, t2_master: float
) -> float:
    """등록 두께 합 대비 실측 두께 합의 변화율을 5% 단위 점수로.

    예) 등록 2.0 mm, 실측 2.4 mm → 20% 변화 → 점수 400.
    재질 정상 + 두께만 다른 시나리오(H) 에서도 의미 있는 페널티가 되도록
    설정되어 있다.
    """
    sum_master = t1_master + t2_master
    if sum_master <= 0:
        return 0.0
    diff_ratio = abs((t1_event + t2_event) - sum_master) / sum_master
    return diff_ratio / _THICKNESS_DEV_UNIT_PCT * 100


def status_from_score(score: float) -> JudgementStatus:
    if score <= _STATUS_NORMAL_MAX:
        return JudgementStatus.NORMAL
    if score <= _STATUS_CAUTION_MAX:
        return JudgementStatus.CAUTION
    return JudgementStatus.REJECT


# --------------------------------------------------------------------------- #
# 통합 진입점
# --------------------------------------------------------------------------- #


async def evaluate(
    event: WeldEvent,
    part: Part,
    config: WeldingConfig,
) -> Judgement | None:
    """타점 이벤트 평가 엔진.

    1) F-04 강제 격상 사전 체크 — 매치 시 즉시 반환.
    2) F-05 점수 산출 → 상태 분기.
    """
    forced = check_forced_escalation(event, part, config)
    if forced is not None:
        return forced

    score, deviations = compute_score(event, part, config)
    return Judgement(
        score=score,
        status=status_from_score(score),
        forced_reason=None,
        deviations=deviations,
    )
