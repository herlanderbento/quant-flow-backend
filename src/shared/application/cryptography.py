from abc import ABC, abstractmethod


class IPasswordHasher(ABC):
    """Contract for irreversible hashing — used in user passwords and exchange API secrets."""

    @abstractmethod
    def hash(self, plain: str) -> str:
        pass

    @abstractmethod
    def verify(self, plain: str, hashed: str) -> bool:
        pass


class IEncryption(ABC):
    """Contract for reversible encryption — used in exchange API secrets."""

    @abstractmethod
    def encrypt(self, plain: str) -> str:
        pass

    @abstractmethod
    def decrypt(self, encrypted: str) -> str:
        pass