from abc import ABC, abstractmethod
from typing import Any, List, Set, Type, Optional, TypeVar, Generic

from shared.domain.value_objects import ValueObject
from shared.domain.entity import AggregateRoot


E = TypeVar("E", bound=AggregateRoot)
EntityId = TypeVar("EntityId", bound=ValueObject)


class IRepository(ABC, Generic[E, EntityId]):
    @abstractmethod
    def insert(self, entity: E) -> None:
        raise NotImplementedError()

    @abstractmethod
    def bulk_insert(self, entities: List[E]) -> None:
        raise NotImplementedError()

    @abstractmethod
    def find_by_id(self, entity_id: EntityId) -> Optional[E]:
        raise NotImplementedError()

    @abstractmethod
    def find_all(self) -> List[E]:
        raise NotImplementedError()

    @abstractmethod
    def find_by_ids(self, entity_ids: Set[EntityId]) -> List[E]:
        raise NotImplementedError()

    @abstractmethod
    def update(self, entity: E) -> None:
        raise NotImplementedError()

    @abstractmethod
    def delete(self, entity_id: EntityId) -> None:
        raise NotImplementedError()

    @abstractmethod
    def get_entity(self) -> Type[E]:
        raise NotImplementedError()


Filter = TypeVar("Filter", bound=str)
SearchInput = TypeVar("SearchInput")
SearchOutput = TypeVar("SearchOutput")


class ISearchableRepository(Generic[E, EntityId], IRepository[E, EntityId], ABC):

    sortable_fields: List[str] = []

    @abstractmethod
    def search(self, props: Any) -> Any:
        raise NotImplementedError()
