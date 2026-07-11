from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr
from account.application.use_cases.user.common.user_output import UserOutput
from account.application.use_cases.user.list_users import ListUsersOutput
from shared.infra.api.presenter import CollectionPresenter, meta_from_output


class UserPresenter(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    is_active: bool | None
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_output(cls, output: UserOutput) -> "UserPresenter":
        return cls(
            id=output.id,
            name=output.name,
            email=output.email,
            is_active=output.is_active,
            created_at=output.created_at,
            updated_at=output.updated_at,
        )


class UserCollectionPresenter(CollectionPresenter[UserPresenter]):
    @classmethod
    def from_output(cls, output: ListUsersOutput) -> "UserCollectionPresenter":
        return cls(
            data=[UserPresenter.from_output(item) for item in output.items],
            meta=meta_from_output(output),
        )
