"""사용자 / 인증 — 서비스 레이어.

비밀번호 해시: PBKDF2-HMAC-SHA256, 16-byte 솔트, 200k 라운드. stdlib 만 사용.
세션 토큰: `secrets.token_urlsafe(32)` (256-bit). 1인 1세션 — 새 로그인은
기존 토큰을 무효화한다.

`hash_password` / `verify_password` 는 순수 함수 — 테스트하기 좋다.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppException
from app.models.user import User, UserRole


_PBKDF2_ITER = 200_000
_PBKDF2_SALT_BYTES = 16
_SESSION_LIFETIME = timedelta(days=30)


def hash_password(plain: str) -> str:
    """`{salt_hex}:{pbkdf2_hex}` 형식 문자열로 반환."""
    salt = secrets.token_bytes(_PBKDF2_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, _PBKDF2_ITER
    )
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    """타이밍 안전 비교. 포맷 깨졌으면 False (예외 X)."""
    try:
        salt_hex, digest_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, _PBKDF2_ITER
    )
    return hmac.compare_digest(digest, expected)


def _new_token() -> str:
    return secrets.token_urlsafe(32)


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #


async def create_user(
    *,
    username: str,
    password: str,
    display_name: str,
    role: UserRole = UserRole.WORKER,
) -> User:
    """username unique 충돌 시 409."""
    user = User(
        username=username,
        display_name=display_name,
        role=role,
        password_hash=hash_password(password),
    )
    try:
        await user.insert()
    except DuplicateKeyError as e:
        key = list((e.details or {}).get("keyPattern", {}).keys())
        if "username" in key:
            raise AppException(
                message=f"이미 사용 중인 사용자 ID 입니다: {username}",
                code=409,
            )
        raise AppException(message=f"중복 키 오류: {key}", code=409)
    return user


async def get_user_by_username(username: str) -> User | None:
    return await User.find_one(User.username == username)


async def get_user_by_token(token: str) -> User | None:
    """만료된 토큰은 None. 호출자가 401 로 분기."""
    if not token:
        return None
    user = await User.find_one(User.session_token == token)
    if user is None:
        return None
    expires_at = user.session_expires_at
    if expires_at is None:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    return user


# --------------------------------------------------------------------------- #
# 로그인 / 로그아웃
# --------------------------------------------------------------------------- #


async def login(
    *, username: str, password: str
) -> tuple[User, str, datetime]:
    """성공 시 (user, token, expires_at) 반환. 실패 시 401.

    실패 메시지는 의도적으로 '아이디 또는 비밀번호' 로 통합 — username 존재
    여부 leak 방지.
    """
    user = await get_user_by_username(username)
    if user is None or not verify_password(password, user.password_hash):
        raise AppException(
            message="아이디 또는 비밀번호가 올바르지 않습니다.",
            code=401,
        )

    now = datetime.now(timezone.utc)
    token = _new_token()
    expires_at = now + _SESSION_LIFETIME

    user.session_token = token
    user.session_expires_at = expires_at
    user.last_login_at = now
    user.updated_at = now
    await user.save()

    return user, token, expires_at


async def logout(user: User) -> None:
    user.session_token = None
    user.session_expires_at = None
    user.updated_at = datetime.now(timezone.utc)
    await user.save()
