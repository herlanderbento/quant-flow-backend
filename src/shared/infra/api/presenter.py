from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

ItemPresenterT = TypeVar("ItemPresenterT", bound=BaseModel)


class MetaPresenter(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    total: int
    current_page: int
    per_page: int
    last_page: int


def meta_from_output(output: Any) -> MetaPresenter:
    return MetaPresenter(
        total=output.total,
        current_page=output.current_page,
        per_page=output.per_page,
        last_page=output.last_page,
    )


class CollectionPresenter(BaseModel, Generic[ItemPresenterT]):
    data: list[ItemPresenterT]
    meta: MetaPresenter
