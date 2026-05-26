"""FastAPI 인증 의존성.

`current_user` 는 Authorization: Bearer <token> 헤더를 검증하고 활성 User
도큐먼트를 반환한다. 토큰 없음/만료/위조 시 401.

라우터에서:
    @router.get("/users/me")
    async def me(user: User = Depends(current_user)):
        ...
"""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import AppException
from app.models.user import User, UserRole
from app.services.user_service import get_user_by_token

_bearer = HTTPBearer(auto_error=False)


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    """Authorization: Bearer <token> 필수. 누락/잘못/만료 → 401."""
    if credentials is None:
        raise AppException(message="인증이 필요합니다.", code=401)
    user = await get_user_by_token(credentials.credentials)
    if user is None:
        raise AppException(message="세션이 만료되었거나 유효하지 않습니다.", code=401)
    return user


def require_role(*roles: UserRole):
    """역할 가드 의존성. `Depends(require_role(UserRole.ADMIN))` 형태로 사용."""

    async def _guard(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise AppException(message="권한이 없습니다.", code=403)
        return user

    return _guard
