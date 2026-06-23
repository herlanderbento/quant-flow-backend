from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
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


def _validation_message(error_type: str, field: str) -> str:
    messages = {
        "missing": f"The field '{field}' is required.",
        "string_too_short": f"The field '{field}' cannot be empty.",
        "string_type": f"The field '{field}' must be a string.",
        "bool_parsing": f"The field '{field}' must be true or false.",
        "bool_type": f"The field '{field}' must be true or false.",
    }
    return messages.get(error_type, f"The field '{field}' is invalid.")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _request: Request, exc: RequestValidationError
    ):
        errors = []
        for error in exc.errors():
            location = [str(part) for part in error["loc"] if part != "body"]
            field = location[-1] if location else "body"
            errors.append(
                {
                    "field": ".".join(location),
                    "message": _validation_message(error["type"], field),
                }
            )
        return JSONResponse(
            status_code=422,
            content={"message": "Invalid data.", "errors": errors},
        )

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
