from typing import Any, Generic, Optional, TypeVar

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Standard envelope returned by every endpoint."""

    success: bool = Field(..., description="요청 성공 여부")
    code: int = Field(..., description="HTTP 상태 코드")
    message: str = Field(..., description="결과 메시지")
    data: Optional[T] = Field(None, description="응답 데이터")


def success_response(
    data: Any = None,
    message: str = "OK",
    code: int = 200,
) -> JSONResponse:
    payload = ApiResponse[Any](
        success=True, code=code, message=message, data=data
    ).model_dump(mode="json")
    return JSONResponse(status_code=code, content=jsonable_encoder(payload))


def error_response(
    message: str,
    code: int = 400,
    data: Any = None,
) -> JSONResponse:
    payload = ApiResponse[Any](
        success=False, code=code, message=message, data=data
    ).model_dump(mode="json")
    return JSONResponse(status_code=code, content=jsonable_encoder(payload))
