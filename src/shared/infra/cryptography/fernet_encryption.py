from cryptography.fernet import Fernet
from shared.application.cryptography import IEncryption
from shared.infra.db.config import settings


class FernetEncryption(IEncryption):
    def __init__(self):
        self._fernet = Fernet(settings.ENCRYPTION_KEY.encode())

    def encrypt(self, plain: str) -> str:
        return self._fernet.encrypt(plain.encode()).decode()

    def decrypt(self, encrypted: str) -> str:
        return self._fernet.decrypt(encrypted.encode()).decode()