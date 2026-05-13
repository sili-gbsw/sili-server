from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.response import ApiResponse, success_response
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    response_model=ApiResponse[list[UserRead]],
    summary="사용자 목록 조회",
)
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.id))
    users = [UserRead.model_validate(u) for u in result.scalars().all()]
    return success_response(data=[u.model_dump(mode="json") for u in users])


@router.post(
    "",
    response_model=ApiResponse[UserRead],
    status_code=status.HTTP_201_CREATED,
    summary="사용자 생성",
)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    user = User(email=payload.email, name=payload.name)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise AppException(message="이미 등록된 이메일입니다.", code=409)
    await db.refresh(user)
    return success_response(
        data=UserRead.model_validate(user).model_dump(mode="json"),
        message="Created",
        code=201,
    )


@router.get(
    "/{user_id}",
    response_model=ApiResponse[UserRead],
    summary="사용자 단건 조회",
)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if user is None:
        raise AppException(message="사용자를 찾을 수 없습니다.", code=404)
    return success_response(
        data=UserRead.model_validate(user).model_dump(mode="json")
    )
