from abc import ABC, abstractmethod


class ITokenGenerator(ABC):
    @abstractmethod
    def generate(self, payload: dict) -> str:
        pass
