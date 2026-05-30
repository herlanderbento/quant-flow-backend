from dataclasses import dataclass
from typing import Generic, TypeVar, TypedDict

from shared.domain.search_input import SortDirection, SortDirectionValues

Filter = TypeVar("Filter", bound=str)

@dataclass(slots=True)
class PaginatedListInput(Generic[Filter]):
    page: int | None = None
    per_page: int | None = None
    sort: str | None = None
    sort_dir: SortDirection | SortDirectionValues | None = None
    filter: Filter | None = None

    def to_search_input(self):
        typed_dict = TypedDict(
            "PaginatedListInput",
            {
                "init_page": int | None,
                "init_per_page": int | None,
                "init_sort": str | None,
                "init_sort_dir": SortDirection | SortDirectionValues | None,
                "init_filter": Filter | None,
            },
        )
        return typed_dict(
            init_page=self.page,
            init_per_page=self.per_page,
            init_sort=self.sort,
            init_sort_dir=self.sort_dir,
            init_filter=self.filter,
        )