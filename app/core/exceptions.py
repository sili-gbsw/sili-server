from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.response import error_response


class AppException(Exception):
    """Domain-level exception carrying an HTTP-like status code and message."""

    def __init__(self, message: str, code: int = 400, data=None):
        self.message = message
        self.code = code
        self.data = data
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(_: Request, exc: AppException):
        return error_response(message=exc.message, code=exc.code, data=exc.data)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException):
        return error_response(message=str(exc.detail), code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError):
        return error_response(
            message="Validation Error",
            code=422,
            data=exc.errors(),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception):
        return error_response(message="Internal Server Error", code=500)
