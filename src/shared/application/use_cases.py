from abc import ABC, abstractmethod
from typing import TypeVar, Generic

Input = TypeVar("Input")
Output = TypeVar("Output")

class UseCase(ABC, Generic[Input, Output]):
    @abstractmethod
    def execute(self, input: Input) -> Output:
        pass