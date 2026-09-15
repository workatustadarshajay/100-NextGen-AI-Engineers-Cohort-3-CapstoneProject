import hashlib
import hmac
import secrets

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

_HASH_NAME = "sha256"
_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(_HASH_NAME, password.encode(), bytes.fromhex(salt), _ITERATIONS).hex()
    return f"{salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    salt, _, digest = password_hash.partition("$")
    if not digest:
        return False
    candidate = hashlib.pbkdf2_hmac(_HASH_NAME, password.encode(), bytes.fromhex(salt), _ITERATIONS).hex()
    return hmac.compare_digest(candidate, digest)


async def get_current_user(request: Request, session: AsyncSession) -> User | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return await session.get(User, user_id)
