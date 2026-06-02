from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from shared.domain.search_input import SortDirection, SortDirectionValues

Filter = TypeVar("Filter", bound=str)

@dataclass(slots=True)
class PaginatedListInput(Generic[Filter]):
    page: int | None = None
    per_page: int | None = None
    sort: str | None = None
    sort_dir: SortDirection | SortDirectionValues | None = None
    filter: Filter | None = None

    def to_search_input(self) -> dict[str, Any]:
        return {
            "init_page": self.page,
            "init_per_page": self.per_page,
            "init_sort": self.sort,
            "init_sort_dir": self.sort_dir,
            "init_filter": self.filter,
        }