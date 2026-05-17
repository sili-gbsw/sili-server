"""F-01 공정 데이터 수집 + F-03 학습 + F-07 알림 + F-09 이력 — 서비스 레이어.

ingest_weld_event() 의 처리 흐름 (docs F-01 처리 표):
  1. 필수 필드 검증 — Pydantic 스키마(`WeldEventCreate`) 에서 자동 처리.
  2. 부품 마스터 조회 — 미등록 시 `AppException(404)`.
  3. event_id 발급 후 WeldEvent INSERT.
  4. 판정 엔진(F-04/F-05) 호출 — 결과가 있으면 `judgement` 임베드 후 save.
  5. F-06 재검 큐 적재 — 🔴 REJECT 또는 강제 격상 시 자동 enqueue.
  6. F-07 알림 푸시 — 인-프로세스 브로드캐스터로 전송 (구독자 없으면 no-op).
  7. F-03 학습 표본 누적 — 활성 세션이 있으면 sample_count 증가.
  8. 최종 WeldEvent 반환.

F-09 조회·내보내기 (읽기 전용)
  - list_weld_events(): 필터(part_id/point_id/status/from/to) + 페이지네이션.
  - get_weld_event(): event_id 단건 조회.
  - get_latest_weld_event(): F-07 폴링용 최신 판정 결과.
  - stream_weld_events_csv(): 컬렉션 전체 적재 없이 CSV 한 줄씩 yield.
"""

import csv
import io
import secrets
from datetime import datetime
from typing import Any, AsyncIterator

from app.core.exceptions import AppException
from app.models.weld_event import JudgementStatus, WeldEvent
from app.schemas.weld_event import WeldEventRead
from app.services.config_service import get_or_init_config
from app.services.judgement import evaluate
from app.services.learning_service import update_learning_from_event
from app.services.notifier import notifier
from app.services.part_service import get_part
from app.services.reinspection_service import enqueue_from_judgement


def generate_event_id() -> str:
    """`evt_` + 24자 hex. 충돌 확률 무시 가능 (96 bit)."""
    return f"evt_{secrets.token_hex(12)}"


async def ingest_weld_event(payload: dict[str, Any]) -> WeldEvent:
    # 1. 부품 마스터 조회 — 미등록 시 AppException(404) 자동 발생.
    part = await get_part(payload["part_id"])

    # 2. 시스템 설정 로드 (판정 엔진에 전달).
    config = await get_or_init_config()

    # 3. WeldEvent 저장.
    event = WeldEvent(event_id=generate_event_id(), **payload)
    await event.insert()

    # 4. 판정 엔진 호출 (F-04/F-05).
    judgement = await evaluate(event, part, config)
    if judgement is not None:
        event.judgement = judgement
        await event.save()
        # 5. F-06 재검 큐 등록 (대상 아닐 시 no-op).
        await enqueue_from_judgement(event, judgement)
        # 6. F-07 알림 푸시 (구독자 없으면 no-op).
        await notifier.publish(
            {
                "type": "judgement",
                "data": WeldEventRead.from_document(event).model_dump(mode="json"),
            }
        )
    # 7. F-03 학습 표본 누적 (활성 세션 없으면 no-op). 판정 유무와 무관.
    await update_learning_from_event(event)

    return event


# --------------------------------------------------------------------------- #
# F-09 이력·추적성 (읽기 전용)
# --------------------------------------------------------------------------- #


async def get_weld_event(event_id: str) -> WeldEvent:
    """단건 조회. 미존재 시 404."""
    event = await WeldEvent.find_one(WeldEvent.event_id == event_id)
    if event is None:
        raise AppException(
            message=f"이벤트를 찾을 수 없습니다: event_id={event_id}",
            code=404,
        )
    return event


async def get_latest_weld_event(
    *, status: JudgementStatus | None = None
) -> WeldEvent | None:
    """F-07 폴링용. 판정이 있는 가장 최근 이벤트 1건. 없으면 None.

    `status` 가 주어지면 해당 상태로 필터링(예: 최근 REJECT 만 조회).
    """
    query: dict[str, Any] = {"judgement": {"$ne": None}}
    if status is not None:
        query["judgement.status"] = status.value
    docs = (
        await WeldEvent.find(query)
        .sort(-WeldEvent.timestamp)
        .limit(1)
        .to_list()
    )
    return docs[0] if docs else None


async def list_weld_events(
    *,
    part_id: str | None = None,
    point_id: str | None = None,
    status: JudgementStatus | None = None,
    from_: datetime | None = None,
    to: datetime | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[WeldEvent]:
    """필터 + 페이지네이션. 최신순(timestamp 내림차순)."""
    query = _build_query(
        part_id=part_id,
        point_id=point_id,
        status=status,
        from_=from_,
        to=to,
    )
    return (
        await WeldEvent.find(query)
        .sort(-WeldEvent.timestamp)
        .skip(skip)
        .limit(limit)
        .to_list()
    )


_CSV_HEADERS = [
    "event_id",
    "timestamp",
    "part_id",
    "point_id",
    "current_kA",
    "weld_time_cycle",
    "force_kN",
    "cumulative_hits",
    "t1",
    "t2",
    "material_code",
    "electrode_shape",
    "judgement_score",
    "judgement_status",
    "judgement_forced_reason",
]


async def stream_weld_events_csv(
    *,
    part_id: str | None = None,
    point_id: str | None = None,
    status: JudgementStatus | None = None,
    from_: datetime | None = None,
    to: datetime | None = None,
) -> AsyncIterator[bytes]:
    """타점 이력을 CSV로 스트리밍 (한 줄 단위 yield).

    대용량 컬렉션을 메모리에 한꺼번에 올리지 않도록 Motor 비동기 커서를
    그대로 소비한다. 정렬은 최신순(`timestamp desc`).
    재질·두께·등급·전극형상 필수 컬럼은 docs F-09 명세 따라 포함.
    """
    query = _build_query(
        part_id=part_id,
        point_id=point_id,
        status=status,
        from_=from_,
        to=to,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    writer.writerow(_CSV_HEADERS)
    yield buffer.getvalue().encode("utf-8")
    buffer.seek(0)
    buffer.truncate()

    async for doc in WeldEvent.find(query).sort(-WeldEvent.timestamp):
        j = doc.judgement
        writer.writerow(
            [
                doc.event_id,
                doc.timestamp.isoformat(),
                doc.part_id,
                doc.point_id,
                doc.current_kA,
                doc.weld_time_cycle,
                doc.force_kN,
                doc.cumulative_hits,
                doc.t1,
                doc.t2,
                doc.material_code.value,
                doc.electrode_shape.value,
                j.score if j is not None else "",
                j.status.value if j is not None else "",
                j.forced_reason.value
                if j is not None and j.forced_reason is not None
                else "",
            ]
        )
        yield buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate()


def _build_query(
    *,
    part_id: str | None,
    point_id: str | None,
    status: JudgementStatus | None,
    from_: datetime | None,
    to: datetime | None,
) -> dict[str, Any]:
    """F-09 필터를 MongoDB 쿼리 dict로 변환. from > to 면 400."""
    if from_ is not None and to is not None and from_ > to:
        raise AppException(
            message="시간 범위가 잘못되었습니다: from > to",
            code=400,
        )

    query: dict[str, Any] = {}
    if part_id is not None:
        query["part_id"] = part_id
    if point_id is not None:
        query["point_id"] = point_id
    if status is not None:
        # judgement 는 임베드. dot-path 로 필터.
        query["judgement.status"] = status.value
    if from_ is not None or to is not None:
        ts: dict[str, datetime] = {}
        if from_ is not None:
            ts["$gte"] = from_
        if to is not None:
            ts["$lte"] = to
        query["timestamp"] = ts
    return query
