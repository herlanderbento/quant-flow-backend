from typing import Any, List


class EntityValidationException(Exception):
    def __init__(self, errors: str = "Entity validation error occurred."):
        super().__init__(errors)


class NotFoundException(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class ConflictException(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class ForbiddenException(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class InvalidArgumentException(Exception):
    def __init__(self, message):
        super().__init__(message)


class UnauthorizedException(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class InvalidUuidException(Exception):
    def __init__(self, uuid: str):
        super().__init__(f"ID {uuid} must be a valid UUID")

class GatewayException(Exception):
    def __init__(self, message: str):
        super().__init__(message)