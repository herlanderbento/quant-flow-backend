from typing import Any, List


class NotFoundException(Exception):
    def __init__(self, _id: Any | List[Any], entity_name: str):
        if isinstance(_id, list):
            _id = ", ".join(str(i) for i in _id)
        super().__init__(f"{entity_name.__name__} with id {_id} not found")

class EntityValidationException(Exception):
    def __init__(self, errors: str = "Entity validation error occurred."):
        super().__init__(errors)


class NotFoundException(Exception):
    def __init__(self, message: str):
        super().__init__(message)

class ConflictException(Exception):
    def __init__(self, message: str):
        super().__init__(message)

class InvalidArgumentException(Exception):
    def __init__(self, message):
        super().__init__(message)

class InvalidUuidException(Exception):
  def __init__(self, uuid: str):
    super().__init__(f"ID {uuid} must be a valid UUID")