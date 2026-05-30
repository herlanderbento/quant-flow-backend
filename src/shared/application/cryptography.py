from abc import ABC, abstractmethod


class ICryptography(ABC):
    @abstractmethod
    def verify(self, plain: str, hash: str) -> bool:
        pass

    @abstractmethod
    def hash(self, plain: str) -> str:
        pass
