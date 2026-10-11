

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


class TradingModeException(Exception):
    """The configured trading mode forbids the requested gateway."""


class UnsafeCredentialException(Exception):
    """The API key has permissions the bot must never hold (e.g. withdrawals)."""


class OrderRejectedException(GatewayException):
    """The exchange definitively refused the order: nothing was executed."""


class OrderStateUnknownException(GatewayException):
    """The order may or may not exist on the exchange; it must be reconciled."""
