"""사용자 모델 — Beanie Document.

v1 경량 인증: username + password(PBKDF2-SHA256 + 솔트) + 세션 토큰.
JWT 도 password-hash 라이브러리(bcrypt/argon2) 도 외부 의존 없이 stdlib
만 사용한다. 경진대회 데모 범위에서 충분히 안전한 수준.

토큰 만료는 30일. 만료된 토큰은 인증 의존성에서 거절된다.
"""

from datetime import datetime, timezone
from enum import Enum

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class UserRole(str, Enum):
    """역할 — 인가 분기용. v1 에서는 admin/qa/worker 셋만."""

    ADMIN = "admin"
    QA = "qa"
    WORKER = "worker"


class User(Document):
    """사용자 도큐먼트 (`users` 컬렉션).

    `username` 이 unique 인덱스로 보호된다. 비밀번호는 평문 저장 절대 금지 —
    `password_hash`(salt+hash) 만 영구 저장.
    `session_token` 은 현재 활성 토큰(단일 세션 정책). 새 로그인 시 교체.
    """

    username: str = Field(
        ..., min_length=3, max_length=64, description="로그인 식별자."
    )
    display_name: str = Field(
        ..., max_length=120, description="사이드바·프로필 표시명."
    )
    role: UserRole = Field(
        default=UserRole.WORKER, description="역할(admin/qa/worker)."
    )
    password_hash: str = Field(
        ...,
        description="`{salt_hex}:{pbkdf2_hex}` 형식. user_service.hash_password 산출.",
    )

    session_token: str | None = Field(
        default=None,
        description="현재 활성 세션 토큰. 로그아웃·재로그인 시 갱신.",
    )
    session_expires_at: datetime | None = Field(
        default=None, description="세션 만료 시각 (UTC)."
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_login_at: datetime | None = Field(default=None)

    class Settings:
        name = "users"
        indexes = [
            IndexModel("username", unique=True),
            IndexModel("session_token", sparse=True),
        ]
