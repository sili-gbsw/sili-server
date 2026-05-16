"""F-04 (강제 격상) + F-05 (판정 엔진) — placeholder.

Phase 1 (F-01 ingestion) 단계에서는 미구현 상태이다. `evaluate()` 가
`None` 을 반환하면 ingestion 흐름은 `WeldEvent.judgement` 를 `None` 그대로
저장한다 (= 판정 대기).

Phase 2 에서 이 한 함수만 채우면 F-01 코드 수정 없이 ingest → 즉시 판정
흐름이 활성화된다.

판정 알고리즘 (docs 10절 참고):
  1. (F-04) 강제 격상 사전 체크 — 재질 불일치 / 두께 비 1:3 초과 /
     전극 형상 불일치 → forced_reason 채워서 즉시 반환
  2. (F-05) MILD 기준값 + 재질 보정 → 등급별 허용 편차로 정규화 →
     파라미터별 이탈률 × 가중치 합산 → 0~100 점수 → 상태 분기
"""

from app.models.part import Part
from app.models.weld_event import Judgement, WeldEvent
from app.models.welding_config import WeldingConfig


async def evaluate(
    event: WeldEvent,
    part: Part,
    config: WeldingConfig,
) -> Judgement | None:
    """타점 이벤트를 평가하여 판정 결과를 반환. 미구현 시 None.

    Args:
        event: 방금 저장된 WeldEvent (스냅샷 필드 포함).
        part: 부품 마스터 (config 로드 키 조회용).
        config: 시스템 동적 설정 (두께·재질·등급·전극형상 규칙).

    Returns:
        판정 완료 시 Judgement. 미구현/판정 보류 시 None.
    """
    # F-04/F-05 구현 위치. Phase 2 에서 채운다.
    return None
