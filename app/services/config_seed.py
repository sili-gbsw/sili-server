"""F-10. 설정(Config) 관리 — 기본값 시드 모듈.

애플리케이션 부팅 시 1회 호출되어 MongoDB `config` 컬렉션에 싱글톤
도큐먼트가 존재하는지 확인하고, 없으면 `welding_defaults.DEFAULT_WELDING_CONFIG`
(docs/v1_아이디어_구체화.md 15절 기반) 값으로 1건 시드한다.

설계 원칙
- **멱등(idempotent)**: 이미 존재하면 그대로 반환, 추가 INSERT 없음.
- **레이스 안전**: 멀티 워커 동시 부팅 시 `singleton_key` unique 인덱스가
  중복 INSERT를 차단하므로 DuplicateKeyError를 잡고 기존 도큐먼트를 재조회한다.
- **추적성**: 최초 시드 시 ConfigAudit(`key="__seed__"`) 1건을 남겨서
  "이 컬렉션이 언제, 무엇으로 초기화되었는가"를 운영 로그로 보존한다.
- **검증**: WeldingConfig 모델 생성 단계에서 Pydantic 스키마 검증을 거치므로
  기본값에 오타가 있으면 부팅 단계에서 즉시 실패한다.
"""

from __future__ import annotations

import logging

from pymongo.errors import DuplicateKeyError

from app.models.welding_config import ConfigAudit, WeldingConfig
from app.services.welding_defaults import DEFAULT_WELDING_CONFIG

logger = logging.getLogger(__name__)

SINGLETON_KEY = "default"
SEED_AUDIT_KEY = "__seed__"
SEED_AUDIT_ACTOR = "system"


async def seed_default_config() -> WeldingConfig:
    """`config` 싱글톤을 보장한다. 없으면 기본값으로 1건 생성하고 반환.

    Returns:
        시드된(또는 기존의) WeldingConfig 도큐먼트.
    """
    existing = await _find_singleton()
    if existing is not None:
        logger.info(
            "config seed skipped: singleton already present (version=%s)",
            existing.version,
        )
        return existing

    config = WeldingConfig(
        singleton_key=SINGLETON_KEY,
        version=1,
        **DEFAULT_WELDING_CONFIG,
    )
    try:
        await config.insert()
    except DuplicateKeyError:
        winner = await _find_singleton()
        if winner is None:
            raise
        logger.info(
            "config seed race resolved: another worker seeded first "
            "(version=%s)",
            winner.version,
        )
        return winner

    await ConfigAudit(
        key=SEED_AUDIT_KEY,
        old_value=None,
        new_value={
            "version": config.version,
            "source": "DEFAULT_WELDING_CONFIG",
        },
        changed_by=SEED_AUDIT_ACTOR,
    ).insert()

    logger.info(
        "config seeded with defaults (version=%s, thickness_combos=%d, "
        "material_codes=%d)",
        config.version,
        len(config.thickness_limits),
        len(config.material_profiles),
    )
    return config


async def _find_singleton() -> WeldingConfig | None:
    return await WeldingConfig.find_one(
        WeldingConfig.singleton_key == SINGLETON_KEY
    )
