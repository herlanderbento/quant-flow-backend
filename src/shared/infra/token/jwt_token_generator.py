from datetime import UTC, datetime, timedelta

import jwt

from shared.application.token_generator import ITokenGenerator
from shared.infra.db.config import settings


class JwtTokenGenerator(ITokenGenerator):
    def generate(self, payload: dict) -> str:
        token_type = payload.get("type", "access")
        subject = payload["sub"]

        if token_type == "refresh":
            expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        else:
            expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        expire = datetime.now(UTC) + expires_delta
        claims = {
            "sub": subject,
            "type": token_type,
            "exp": expire,
        }

        return jwt.encode(
            claims,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
