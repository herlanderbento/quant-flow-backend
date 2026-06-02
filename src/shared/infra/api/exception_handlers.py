from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from shared.domain.exceptions import (
    ConflictException,
    EntityValidationException,
    InvalidArgumentException,
    InvalidUuidException,
    NotFoundException,
    UnauthorizedException,
)


def _error_response(status_code: int, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": str(exc)})


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundException)
    async def not_found_handler(_request: Request, exc: NotFoundException):
        return _error_response(404, exc)

    @app.exception_handler(ConflictException)
    async def conflict_handler(_request: Request, exc: ConflictException):
        return _error_response(409, exc)

    @app.exception_handler(EntityValidationException)
    async def validation_handler(_request: Request, exc: EntityValidationException):
        return _error_response(422, exc)

    @app.exception_handler(UnauthorizedException)
    async def unauthorized_handler(_request: Request, exc: UnauthorizedException):
        return _error_response(401, exc)

    @app.exception_handler(InvalidArgumentException)
    async def invalid_argument_handler(_request: Request, exc: InvalidArgumentException):
        return _error_response(400, exc)

    @app.exception_handler(InvalidUuidException)
    async def invalid_uuid_handler(_request: Request, exc: InvalidUuidException):
        return _error_response(400, exc)
