from dataclasses import dataclass, field
import math
from typing import Any, Generic, List, TypeVar

SearchOutputItem = TypeVar("SearchOutputItem", bound=Any)

@dataclass(slots=True, kw_only=True)
class SearchOutput(Generic[SearchOutputItem]):
    items: List[SearchOutputItem]
    total: int
    current_page: int
    per_page: int
    last_page: int = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "last_page", math.ceil(self.total / self.per_page))