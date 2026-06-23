
from shared.application.cryptography import IEncryption, IPasswordHasher
from shared.infra.cryptography.bcrypt_hasher import BcryptHasher
from shared.infra.cryptography.fernet_encryption import FernetEncryption


def get_encryption() -> IEncryption:
    return FernetEncryption()

def get_bcrypt_hasher() -> IPasswordHasher:
    return BcryptHasher()