from dataclasses import dataclass
from typing import Any, Generic, List, TypeVar

from shared.domain.search_output import SearchOutput

OutputItem = TypeVar("OutputItem")

@dataclass(slots=True)
class PaginatedListOutput(Generic[OutputItem]):
    items: List[OutputItem]
    total: int
    current_page: int
    per_page: int
    last_page: int

    @classmethod
    def from_search_output(
        cls,
        items: List[OutputItem],
        output: SearchOutput[Any],
    ):
        last_page = max(1, (output.total + output.per_page - 1) // output.per_page)

        return cls(
            items=items,
            total=output.total,
            current_page=output.current_page,
            per_page=output.per_page,
            last_page=last_page,
        )
