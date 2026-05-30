from dataclasses import Field, InitVar, dataclass, field
from enum import Enum
from typing import Any, Generic, Literal, Optional, TypeVar, cast, get_args


class SortDirection(Enum):
    ASC = "asc"
    DESC = "desc"

    def equals(self, value: Any):
        return value.lower() == self.value


SortDirectionValues = Literal["asc", "desc"]

Filter = TypeVar("Filter")


@dataclass(slots=True, kw_only=True)
class SearchInput(Generic[Filter]):
    page: int = field(init=False, default=1)
    per_page: int = field(init=False, default=15)
    sort: str | None = field(init=False, default=None)
    sort_dir: SortDirection | None = field(init=False, default=None)
    filter: Filter | None = field(init=False, default=None)

    init_page: Optional[InitVar[int | None]] = None
    init_per_page: Optional[InitVar[int | None]] = None
    init_sort: Optional[InitVar[str | None]] = None
    init_sort_dir: Optional[InitVar[SortDirectionValues | SortDirection | None]] = None
    init_filter: Optional[InitVar[Filter | None]] = None

    def __post_init__(
        self,
        init_page: int | None,
        init_per_page: int | None,
        init_sort: str | None,
        init_sort_dir: SortDirectionValues | SortDirection | None,
        init_filter: Filter | None,
    ):
        self._normalize_page(init_page)
        self._normalize_per_page(init_per_page)
        self._normalize_sort(init_sort)
        self._normalize_sort_dir(init_sort_dir)
        self._normalize_filter(init_filter)

    def _normalize_page(self, page: int | None):
        page = _int_or_none(page)
        if page <= 0:
            page = cast(int, self.get_field("page").default)
        self.page = page

    def _normalize_per_page(self, per_page: int | None):
        per_page = _int_or_none(per_page)
        if per_page < 1:
            per_page = cast(int, self.get_field("per_page").default)
        self.per_page = per_page

    def _normalize_sort(self, sort: str | None):
        sort = None if sort == "" or sort is None else str(sort)
        self.sort = sort

    def _normalize_sort_dir(self, sort_dir: SortDirectionValues | SortDirection | None):

        if not self.sort:
            self.sort_dir = None
            return

        if isinstance(sort_dir, SortDirection):
            self.sort_dir = sort_dir
            return

        sort_dir = str(sort_dir).lower()  # type: ignore
        sort_dir = SortDirection.DESC if sort_dir == "desc" else SortDirection.ASC
        self.sort_dir = sort_dir

    def _normalize_filter(self, _filter: Filter | None):
        filter_type = get_args(self.__orig_bases__[0])[0]
        self.filter = _filter if isinstance(_filter, filter_type) else None

    @classmethod
    def get_field(cls, entity_field: str) -> Field[Any]:
        return cls.__dataclass_fields__[entity_field]


def _int_or_none(value: Any, default: int = 0) -> int:
    try:
        return value if isinstance(value, int) else int(value)
    except (ValueError, TypeError):
        return default
