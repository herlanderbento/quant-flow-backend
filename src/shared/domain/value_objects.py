from abc import abstractmethod
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Union
from uuid import uuid4, UUID as PythonUUID

from shared.domain.exceptions import InvalidUuidException


class ValueObject(ABC):
  @abstractmethod
  def equals(self, other: Any) -> bool:
    raise NotImplementedError

@dataclass(frozen=True, slots=True)
class Uuid(ValueObject):
    value: Union[PythonUUID, str] = field(
        default_factory=lambda: uuid4(),
    )

    def __post_init__(self):
        if isinstance(self.value, str):
            object.__setattr__(self, "value", PythonUUID(self.value))
        self.__validate()

    def __validate(self):
        if not isinstance(self.value, PythonUUID):
            raise InvalidUuidException(str(self.value))

    def __str__(self):
        return str(self.value)

    def __eq__(self, __value: object) -> bool:
        return self.equals(__value)

    def equals(self, other: Any) -> bool:
        return self.value == other.value if isinstance(other, self.__class__) else False
