import bcrypt

from shared.application.cryptography import IPasswordHasher


class BcryptHasher(IPasswordHasher):
    def verify(self, plain: str, hash: str) -> bool:
        return bcrypt.checkpw(plain.encode("utf-8"), hash.encode("utf-8"))

    def hash(self, plain: str) -> str:
        salt = bcrypt.gensalt(rounds=12)
        hashed_password = bcrypt.hashpw(plain.encode("utf-8"), salt)
        return hashed_password.decode("utf-8")
