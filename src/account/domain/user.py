from dataclasses import dataclass, field
import datetime
from typing import Annotated

from pydantic import Strict

from shared.domain.entity import AggregateRoot
from shared.domain.value_objects import Uuid


@dataclass(slots=True, kw_only=True)
class UserCreateCommand:
    name: str
    email: str
    password: str
    is_active: bool | None = True


class UserId(Uuid):
    pass


@dataclass(slots=True, kw_only=True)
class User(AggregateRoot):
    id: UserId = field(default_factory=UserId)
    name: str
    email: str
    password: str
    is_active: bool | None = True
    created_at: Annotated[datetime.datetime, Strict()] = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    updated_at: Annotated[datetime.datetime, Strict()] = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )

    @staticmethod
    def create(command: UserCreateCommand) -> "User":
        return User(
            name=command.name,
            email=command.email,
            password=command.password,
            is_active=command.is_active
        )

    @property
    def entity_id(self) -> UserId:
        return self.id

    def change_name(self, name: str) -> None:
        self.name = name
        self.touch()

    def change_email(self, email: str) -> None:
        self.email = email
        self.touch()

    def change_password(self, password: str) -> None:
        self.password = password
        self.touch()

    def activate(self) -> None:
        self.is_active = True
        self.touch()

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def touch(self) -> None:
        self.updated_at = datetime.datetime.now(datetime.UTC)

    def validate(self):
        self._validate({
          "id": self.id,
          "name": self.name,
          "email": self.email,
          "password": self.password,
          "is_active": self.is_active,
          "created_at": self.created_at,
          "updated_at": self.updated_at
        })