"""F-03 정상 범위 자동 학습 + F-08 학습 환류 — 서비스 레이어.

세션 라이프사이클
  POST /learning/start  → NormalRangeLearning(COLLECTING) INSERT.
  weld_event ingest     → 활성 세션이 있으면 sample_count 증가.
  sample_count == target → 누적 표본의 μ/σ 산출 → COMPLETE 전이 + INITIAL 이력.
  F-08 (재검 결과 '실제 정상') → 해당 이벤트를 표본에 추가, μ/σ 재산출 + FEEDBACK 이력.
  POST /learning/reset  → 도큐먼트 삭제. 새 학습은 다시 start.

샘플 집계 (Pull-based recompute)
  COMPLETE 전이 / FEEDBACK 시점에 WeldEvent 컬렉션을 일괄 조회해 통계 산출.
  단순·멱등. 표본 수가 매우 큰(>10k) 환경에서는 Welford online 알고리즘으로 교체 권장.

  - 초기 표본: `sample_window_start <= timestamp` + `(line_id, part_id)`, 시간 오름차순 LIMIT target.
  - FEEDBACK 표본: 위 + `feedback_event_ids` 의 이벤트들 (중복 제거).

산출 통계
  - 표본 표준편차(n-1 분모, `statistics.stdev`). 모표준편차가 아님.
  - 표본이 2건 미만이면 σ 산출 불가 → 세션은 COLLECTING 유지하고 카운터만 저장.
"""

from datetime import datetime, timezone
from statistics import mean, stdev
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppException
from app.models.learning import (
    LearningHistoryEntry,
    LearningParams,
    LearningStatus,
    LearningTrigger,
    NormalRangeLearning,
    ParamStats,
)
from app.models.weld_event import WeldEvent


async def start_learning(
    *, line_id: str, part_id: str, target_sample_count: int = 100
) -> NormalRangeLearning:
    """신규 학습 세션 INSERT. 같은 (line_id, part_id) 가 있으면 409."""
    now = datetime.now(timezone.utc)
    session = NormalRangeLearning(
        line_id=line_id,
        part_id=part_id,
        status=LearningStatus.COLLECTING,
        target_sample_count=target_sample_count,
        sample_count=0,
        sample_window_start=now,
    )
    try:
        await session.insert()
    except DuplicateKeyError:
        raise AppException(
            message=(
                f"이미 학습 세션이 존재합니다: line_id={line_id}, "
                f"part_id={part_id}. /learning/reset 후 다시 시작하세요."
            ),
            code=409,
        )
    return session


async def list_learning_sessions(
    *, line_id: str, part_id: str | None = None
) -> list[NormalRangeLearning]:
    """라인별 세션 목록. 부품 ID 필터 옵션. 최근 갱신순."""
    query: dict[str, Any] = {"line_id": line_id}
    if part_id is not None:
        query["part_id"] = part_id
    return (
        await NormalRangeLearning.find(query)
        .sort(-NormalRangeLearning.updated_at)
        .to_list()
    )


async def reset_learning(
    *, line_id: str, part_id: str | None = None
) -> int:
    """세션 삭제. part_id 생략 시 해당 라인 전체 삭제. 삭제 건수 반환."""
    query: dict[str, Any] = {"line_id": line_id}
    if part_id is not None:
        query["part_id"] = part_id
    result = (
        await NormalRangeLearning.get_motor_collection().delete_many(query)
    )
    return result.deleted_count


async def update_learning_from_event(event: WeldEvent) -> None:
    """ingest 흐름 후크. 활성 세션이 있으면 표본 1건 추가.

    COLLECTING 상태가 아닌 세션(COMPLETE) 은 무시. target 도달 시 _finalize.
    """
    session = await NormalRangeLearning.find_one(
        {
            "line_id": event.line_id,
            "part_id": event.part_id,
            "status": LearningStatus.COLLECTING.value,
        }
    )
    if session is None:
        return

    session.sample_count += 1
    session.updated_at = datetime.now(timezone.utc)

    if session.sample_count >= session.target_sample_count:
        await _finalize(session)
    else:
        await session.save()


def _compute_params(events: list[WeldEvent]) -> LearningParams | None:
    """순수 함수. 표본이 2건 미만이면 None (σ 산출 불가)."""
    n = len(events)
    if n < 2:
        return None
    currents = [e.current_kA for e in events]
    times = [e.weld_time_cycle for e in events]
    forces = [e.force_kN for e in events]
    return LearningParams(
        current_kA=ParamStats(
            mean=mean(currents), std=stdev(currents), sample_count=n
        ),
        weld_time_cycle=ParamStats(
            mean=mean(times), std=stdev(times), sample_count=n
        ),
        force_kN=ParamStats(
            mean=mean(forces), std=stdev(forces), sample_count=n
        ),
    )


async def _finalize(session: NormalRangeLearning) -> None:
    """target 도달 시 누적 표본을 조회해 μ/σ 산출, COMPLETE 전이 + INITIAL 이력."""
    docs = (
        await WeldEvent.find(
            {
                "line_id": session.line_id,
                "part_id": session.part_id,
                "timestamp": {"$gte": session.sample_window_start},
            }
        )
        .sort("+timestamp")
        .limit(session.target_sample_count)
        .to_list()
    )
    params = _compute_params(docs)
    if params is None:
        # 통계 산출 불가 — 카운터만 저장하고 COLLECTING 유지.
        await session.save()
        return

    now = datetime.now(timezone.utc)
    session.params = params
    session.status = LearningStatus.COMPLETE
    session.completed_at = now
    session.history.append(
        LearningHistoryEntry(
            timestamp=now,
            trigger=LearningTrigger.INITIAL,
            source_queue_id=None,
            source_event_ids=[],
            sample_count=len(docs),
            params=params,
        )
    )
    await session.save()


# --------------------------------------------------------------------------- #
# F-08 학습 환류
# --------------------------------------------------------------------------- #


async def apply_feedback_to_learning(
    *, queue_id: str, event_ids: list[str]
) -> None:
    """F-08 진입점. 재검 결과 '실제 정상' 인 큐의 event_ids 를 학습에 환류.

    동작
      1. event_ids 로 WeldEvent 조회.
      2. (line_id, part_id) 단위로 그룹화 (큐의 이벤트가 다 같은 부품이라도
         line_id 가 다를 가능성에 대비).
      3. 각 그룹의 COMPLETE 세션을 찾아 표본 추가 + μ/σ 재산출.
      4. 세션이 없거나 COLLECTING 이면 skip (초기 학습이 우선).

    부수효과 없음 — 호출자(reinspection_service)는 best-effort 로 try/except.
    """
    if not event_ids:
        return
    events = await WeldEvent.find({"event_id": {"$in": event_ids}}).to_list()
    if not events:
        return

    by_key: dict[tuple[str, str], list[WeldEvent]] = {}
    for e in events:
        by_key.setdefault((e.line_id, e.part_id), []).append(e)

    for (line_id, part_id), group in by_key.items():
        session = await NormalRangeLearning.find_one(
            {
                "line_id": line_id,
                "part_id": part_id,
                "status": LearningStatus.COMPLETE.value,
            }
        )
        if session is None:
            continue
        await _apply_feedback_to_session(session, queue_id, group)


async def _apply_feedback_to_session(
    session: NormalRangeLearning,
    queue_id: str,
    events: list[WeldEvent],
) -> None:
    """단일 세션에 환류 적용 — 중복 event_id 는 무시 (멱등)."""
    existing = set(session.feedback_event_ids)
    new_ids = [e.event_id for e in events if e.event_id not in existing]
    if not new_ids:
        return

    session.feedback_event_ids.extend(new_ids)
    samples = await _gather_samples(session)
    params = _compute_params(samples)
    if params is None:
        # σ 산출 불가 — 이론상 도달 불가하지만 안전망.
        return

    now = datetime.now(timezone.utc)
    session.params = params
    session.updated_at = now
    session.history.append(
        LearningHistoryEntry(
            timestamp=now,
            trigger=LearningTrigger.FEEDBACK,
            source_queue_id=queue_id,
            source_event_ids=new_ids,
            sample_count=len(samples),
            params=params,
        )
    )
    await session.save()


async def _gather_samples(session: NormalRangeLearning) -> list[WeldEvent]:
    """원본 window 표본 + feedback 표본 합쳐 반환 (event_id 중복 제거)."""
    original = (
        await WeldEvent.find(
            {
                "line_id": session.line_id,
                "part_id": session.part_id,
                "timestamp": {"$gte": session.sample_window_start},
            }
        )
        .sort("+timestamp")
        .limit(session.target_sample_count)
        .to_list()
    )
    original_ids = {e.event_id for e in original}
    feedback_ids = [
        eid for eid in session.feedback_event_ids if eid not in original_ids
    ]
    if not feedback_ids:
        return original
    feedback_events = await WeldEvent.find(
        {"event_id": {"$in": feedback_ids}}
    ).to_list()
    return original + feedback_events


async def get_learning_history(
    *, line_id: str, part_id: str | None = None
) -> list[dict[str, Any]]:
    """라인의 학습 이력 항목들을 세션 키와 함께 flatten 하여 반환.

    각 행: {line_id, part_id, history(=list[LearningHistoryEntry as dict])}.
    세션 단위로 묶어 응답하면 클라이언트가 부품별 그래프를 그리기 편하다.
    """
    query: dict[str, Any] = {"line_id": line_id}
    if part_id is not None:
        query["part_id"] = part_id

    sessions = await NormalRangeLearning.find(query).to_list()
    rows: list[dict[str, Any]] = []
    for s in sessions:
        # 시간순 정렬 (append-only 라 이미 정렬되어 있지만 방어적).
        ordered = sorted(s.history, key=lambda e: e.timestamp)
        rows.append(
            {
                "line_id": s.line_id,
                "part_id": s.part_id,
                "history": [e.model_dump(mode="json") for e in ordered],
            }
        )
    return rows
