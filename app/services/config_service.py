"""F-10. 설정(Config) 관리 — 서비스 레이어.

- get_or_init_config(): MongoDB `config` 컬렉션의 싱글톤을 조회. 부팅 시
  `config_seed.seed_default_config()`가 이미 보장하지만, 시드를 건너뛴
  환경(예: 테스트, 일부 워커)에서도 동작하도록 lazy 보강도 함께 수행한다.
- update_config(): PATCH 동작. 변경 키별 audit 기록 + version bump.
"""

from datetime import datetime, timezone
from typing import Any

from app.models.welding_config import ConfigAudit, WeldingConfig
from app.services.config_seed import SINGLETON_KEY, seed_default_config

# PATCH가 허용하는 최상위 필드 화이트리스트.
PATCHABLE_FIELDS: tuple[str, ...] = (
    "thickness_limits",
    "material_profiles",
    "quality_class_tolerance",
    "electrode_shape_rule",
    "thickness_ratio_limit",
    "electrode_wear_limit",
    "min_pitch_mm",
    "min_lap_mm",
)


async def get_or_init_config() -> WeldingConfig:
    """싱글톤 config 도큐먼트를 반환. 없으면 시드 모듈에 위임하여 1건 생성."""
    return await seed_default_config()


async def update_config(
    updates: dict[str, Any],
    changed_by: str = "system",
) -> WeldingConfig:
    """PATCH. updates에 포함된 필드만 갱신하고, 변경 건당 audit 기록.

    - 동일 값이면 audit 생성 생략, version도 그대로 유지.
    - 변경 1건 이상이면 version += 1, updated_at 갱신.
    """
    config = await get_or_init_config()

    audits: list[ConfigAudit] = []
    changed = False

    for key, new_value in updates.items():
        if key not in PATCHABLE_FIELDS:
            continue
        old_value = getattr(config, key)
        old_serializable = _as_jsonable(old_value)
        if old_serializable == new_value:
            continue

        setattr(config, key, new_value)
        audits.append(
            ConfigAudit(
                key=key,
                old_value=old_serializable,
                new_value=new_value,
                changed_by=changed_by,
            )
        )
        changed = True

    if changed:
        config.version += 1
        config.updated_at = datetime.now(timezone.utc)
        await config.save()
        if audits:
            await ConfigAudit.insert_many(audits)

    return config


async def list_audits(limit: int = 100) -> list[ConfigAudit]:
    return (
        await ConfigAudit.find_all()
        .sort(-ConfigAudit.changed_at)
        .limit(limit)
        .to_list()
    )


def _as_jsonable(value: Any) -> Any:
    """Pydantic 모델 / dict[str, Model] 형태를 JSON 직렬화 가능한 dict로 평탄화."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: _as_jsonable(v) for k, v in value.items()}
    return value
