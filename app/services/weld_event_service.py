"""F-01. 공정 데이터 수집 — 서비스 레이어.

ingest_weld_event() 의 처리 흐름 (docs F-01 처리 표):
  1. 필수 필드 검증 — Pydantic 스키마(`WeldEventCreate`) 에서 자동 처리.
  2. 부품 마스터 조회 — 미등록 시 `AppException(404)`.
  3. event_id 발급 후 WeldEvent INSERT.
  4. 판정 엔진(F-04/F-05) 호출 — 결과가 있으면 `judgement` 임베드 후 save.
  5. 최종 WeldEvent 반환.
"""

import secrets
from typing import Any

from app.models.weld_event import WeldEvent
from app.services.config_service import get_or_init_config
from app.services.judgement import evaluate
from app.services.part_service import get_part


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

    # 4. 판정 엔진 호출 (F-04/F-05). 현재는 placeholder 라 None 반환.
    judgement = await evaluate(event, part, config)
    if judgement is not None:
        event.judgement = judgement
        await event.save()

    return event
