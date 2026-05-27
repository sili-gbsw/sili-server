"""대시보드 KPI 집계 — 교대(shift) 합격률 + 시간당 생산.

교대(shift) 정의는 docs 에 명시되지 않아 단순 규칙으로 산정한다:
  - 클라이언트가 `hours` 윈도우(기본 8h) 를 지정.
  - 라인 필터(`line_id`) 옵션.
  - 합격률 = NORMAL / 판정 완료 건수 (판정 없는 이벤트는 분모에서 제외).
  - 시간당 생산 = 윈도우 내 총 이벤트 수 / 시간수.

이 모듈은 read-only. WeldEvent 컬렉션을 직접 aggregate 한다.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.reinspection import ReinspectionQueue, ReinspectionStatus
from app.models.weld_event import JudgementStatus, WeldEvent


_DEFAULT_HOURS = 8


async def get_shift_stats(
    *,
    hours: int = _DEFAULT_HOURS,
    line_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """교대 윈도우 합격률 + 시간당 생산.

    Args:
        hours: 윈도우 시간 길이. 기본 8h.
        line_id: 필터. None 이면 전체 라인 합산.
        now: 종료 시각(테스트용). None 이면 현재 UTC.

    Returns:
        - window_start, window_end (ISO 8601 UTC)
        - hours: 윈도우 길이
        - total: 윈도우 내 이벤트 수
        - judged: 판정 완료 이벤트 수
        - normal/caution/reject: 상태별 건수
        - pass_rate: 합격률 (0~1, 판정 완료 기준). judged==0 이면 None.
        - hourly_rate: 시간당 생산 (total/hours, 소수점 1자리).
    """
    end = now if now is not None else datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    base: dict[str, Any] = {"timestamp": {"$gte": start, "$lte": end}}
    if line_id is not None:
        base["line_id"] = line_id

    judged_query = {**base, "judgement": {"$ne": None}}
    status_queries = [
        {**base, "judgement.status": s.value} for s in JudgementStatus
    ]

    total, judged, *status_counts = await asyncio.gather(
        WeldEvent.find(base).count(),
        WeldEvent.find(judged_query).count(),
        *[WeldEvent.find(q).count() for q in status_queries],
    )

    counts = {
        s.value.lower(): status_counts[i] for i, s in enumerate(JudgementStatus)
    }

    pass_rate: float | None
    if judged == 0:
        pass_rate = None
    else:
        pass_rate = round(counts["normal"] / judged, 4)

    hourly_rate = round(total / hours, 1) if hours > 0 else 0.0

    return {
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "hours": hours,
        "line_id": line_id,
        "total": total,
        "judged": judged,
        "normal": counts["normal"],
        "caution": counts["caution"],
        "reject": counts["reject"],
        "pass_rate": pass_rate,
        "hourly_rate": hourly_rate,
    }


async def get_hourly_stats(
    *,
    hours: int = 24,
    line_id: str | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """최근 N시간을 1시간 단위 버킷으로 집계.

    Returns:
        hour 0 (가장 오래된 버킷) ~ hour N-1 (가장 최근) 순서의 리스트.
        판정 없는 이벤트는 normal/caution/reject 에 포함되지 않으나 total 에는 포함.
    """
    end = now if now is not None else datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    match: dict[str, Any] = {"timestamp": {"$gte": start, "$lte": end}}
    if line_id is not None:
        match["line_id"] = line_id

    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": {
                    "$floor": {
                        "$divide": [
                            {"$subtract": ["$timestamp", start]},
                            3_600_000,
                        ]
                    }
                },
                "normal": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$judgement.status", JudgementStatus.NORMAL.value]},
                            1,
                            0,
                        ]
                    }
                },
                "caution": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$judgement.status", JudgementStatus.CAUTION.value]},
                            1,
                            0,
                        ]
                    }
                },
                "reject": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$judgement.status", JudgementStatus.REJECT.value]},
                            1,
                            0,
                        ]
                    }
                },
                "total": {"$sum": 1},
            }
        },
    ]

    collection = WeldEvent.get_pymongo_collection()
    rows = await collection.aggregate(pipeline).to_list(length=None)

    bucket_map: dict[int, dict[str, Any]] = {}
    for row in rows:
        h = int(row["_id"])
        if 0 <= h < hours:
            bucket_map[h] = {
                "hour": h,
                "normal": row["normal"],
                "caution": row["caution"],
                "reject": row["reject"],
                "total": row["total"],
            }

    return [
        bucket_map.get(h, {"hour": h, "normal": 0, "caution": 0, "reject": 0, "total": 0})
        for h in range(hours)
    ]


async def get_user_performance_stats(
    *,
    inspector_id: str | None = None,
    hours: int | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """검사자별 퍼포먼스 통계.

    CLOSED 재검 큐를 inspector_id 기준으로 집계한다.

    Args:
        inspector_id: 특정 검사자 필터. None 이면 전체 검사자.
        hours: 윈도우 시간 길이. None 이면 전체 기간.
        now: 종료 시각(테스트용). None 이면 현재 UTC.

    Returns:
        검사자별:
          - inspector_id
          - recheck_count: 처리한 재검 큐 건수
          - monitored_points: 감시한 총 타점 수 (event_ids 합산)
          - defect_count: 실제 불량 건수
          - pass_count: 오탐(정상) 판정 건수
          - pass_rate: 오탐률 (pass_count / recheck_count, 합격으로 처리된 비율)
    """
    end = now if now is not None else datetime.now(timezone.utc)

    query: dict[str, Any] = {"status": ReinspectionStatus.CLOSED.value}
    if hours is not None:
        start = end - timedelta(hours=hours)
        query["closed_at"] = {"$gte": start, "$lte": end}
    if inspector_id is not None:
        query["result.inspector_id"] = inspector_id

    closed_queues = await ReinspectionQueue.find(query).to_list()

    stats: dict[str, dict[str, Any]] = {}
    for q in closed_queues:
        if q.result is None:
            continue
        iid = q.result.inspector_id
        if iid not in stats:
            stats[iid] = {
                "inspector_id": iid,
                "recheck_count": 0,
                "monitored_points": 0,
                "defect_count": 0,
                "pass_count": 0,
            }
        s = stats[iid]
        s["recheck_count"] += 1
        s["monitored_points"] += len(q.event_ids)
        if q.result.is_defect:
            s["defect_count"] += 1
        else:
            s["pass_count"] += 1

    rows: list[dict[str, Any]] = []
    for s in stats.values():
        rc = s["recheck_count"]
        s["pass_rate"] = round(s["pass_count"] / rc, 4) if rc > 0 else None
        rows.append(s)

    rows.sort(key=lambda x: x["recheck_count"], reverse=True)
    return rows
