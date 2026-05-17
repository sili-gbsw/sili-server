"""F-06 재검 큐 관리 + F-08 학습 환류 트리거 — 서비스 레이어.

판정 결과가 큐 등록 조건에 해당하면 자동 호출(`enqueue_from_judgement`)
또는 작업자 API 호출로 `reinspection_queue` 컬렉션을 갱신한다.
재검 결과 등록 시 `is_defect=false` 면 F-08 환류를 best-effort 로 호출.

큐 단위 정책 — **1 트리거 이벤트 = 1 큐**
  같은 부품의 다른 타점이 또 트리거되어도 신규 큐를 만든다 (집계하지 않음).
  같은 부품의 여러 큐를 한 작업 단위로 묶는 그루핑은 클라이언트(작업자 UI)
  책임. 이렇게 두면 동시성 레이스/혼합 사유 누락/재투입 묶음 위험이 구조적
  으로 사라진다 (`event_ids` 는 항상 길이 1).

큐 등록 조건 (`_resolve_reason`)
  - 강제 격상(`judgement.forced_reason` 존재): 1:1 매핑.
  - 강제 격상 없음 + status == REJECT: `SCORE_REJECT`.
  - 그 외 (NORMAL / 강제 격상 없는 CAUTION): 등록 안 함.
"""

import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppException
from app.models.reinspection import (
    ReinspectionQueue,
    ReinspectionReason,
    ReinspectionResult,
    ReinspectionStatus,
)
from app.models.weld_event import Judgement, JudgementStatus, WeldEvent
from app.services.learning_service import apply_feedback_to_learning

logger = logging.getLogger(__name__)


def generate_queue_id() -> str:
    """`rq_` + 24자 hex (96 bit, 충돌 확률 무시 가능)."""
    return f"rq_{secrets.token_hex(12)}"


def _resolve_reason(judgement: Judgement) -> ReinspectionReason | None:
    """판정 결과로부터 큐 등록 사유를 결정. 등록 대상이 아니면 None."""
    if judgement.forced_reason is not None:
        # ForcedReason 값과 ReinspectionReason 값이 동일 문자열로 정의되어 있어
        # 새 ForcedReason 추가 시 매핑이 빠지면 여기서 ValueError 로 즉시 드러난다.
        return ReinspectionReason(judgement.forced_reason.value)
    if judgement.status == JudgementStatus.REJECT:
        return ReinspectionReason.SCORE_REJECT
    return None


async def enqueue_from_judgement(
    event: WeldEvent, judgement: Judgement
) -> ReinspectionQueue | None:
    """판정 결과 발생 직후 자동 호출되는 후크.

    등록 대상이면 트리거 이벤트마다 신규 큐를 INSERT 한다 (집계 없음).
    등록 대상이 아니면 None.
    """
    reason = _resolve_reason(judgement)
    if reason is None:
        return None

    queue = ReinspectionQueue(
        queue_id=generate_queue_id(),
        part_id=event.part_id,
        event_ids=[event.event_id],
        status=ReinspectionStatus.PENDING,
        reason=reason,
    )
    try:
        await queue.insert()
    except DuplicateKeyError:
        # queue_id 충돌은 사실상 불가능하지만 안전망.
        raise AppException(
            message="재검 큐 식별자 충돌. 다시 시도해 주세요.",
            code=500,
        )
    return queue


async def get_queue(queue_id: str) -> ReinspectionQueue:
    queue = await ReinspectionQueue.find_one(
        ReinspectionQueue.queue_id == queue_id
    )
    if queue is None:
        raise AppException(
            message=f"재검 큐를 찾을 수 없습니다: queue_id={queue_id}",
            code=404,
        )
    return queue


async def list_queues(
    *,
    status: ReinspectionStatus | None = None,
    part_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[ReinspectionQueue]:
    """선택적 필터 + 페이지네이션. 생성 최신순 정렬."""
    query: dict[str, Any] = {}
    if status is not None:
        query["status"] = status.value
    if part_id is not None:
        query["part_id"] = part_id
    return (
        await ReinspectionQueue.find(query)
        .sort(-ReinspectionQueue.created_at)
        .skip(skip)
        .limit(limit)
        .to_list()
    )


async def submit_result(
    queue_id: str, payload: dict[str, Any]
) -> ReinspectionQueue:
    """재검 결과 등록 → CLOSED 전이 + F-08 환류 (best-effort).

    CLOSED 큐에 결과를 다시 등록하면 409. `is_defect=false` (실제 정상) 시
    학습 환류를 시도하며, 실패해도 큐 닫힘 자체는 유지된다 (로그만 남김).
    """
    queue = await get_queue(queue_id)
    if queue.status == ReinspectionStatus.CLOSED:
        raise AppException(
            message=f"이미 종료된 재검 큐입니다: queue_id={queue_id}",
            code=409,
        )

    queue.result = ReinspectionResult(**payload)
    queue.status = ReinspectionStatus.CLOSED
    queue.closed_at = datetime.now(timezone.utc)
    await queue.save()

    # F-08: 실제 정상 판정일 때만 환류. 실패해도 큐 close 는 그대로.
    if not queue.result.is_defect:
        try:
            await apply_feedback_to_learning(
                queue_id=queue.queue_id, event_ids=list(queue.event_ids)
            )
        except Exception as exc:
            logger.warning(
                "F-08 feedback failed for queue_id=%s: %s",
                queue.queue_id,
                exc,
                exc_info=True,
            )
    return queue
