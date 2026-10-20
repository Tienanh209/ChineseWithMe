import asyncio
from functools import cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# argon2id with the library's RFC 9106 "low memory" defaults.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# argon2 takes tens of milliseconds of CPU: keep it off the event loop.
async def ahash_password(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def averify_password(password_hash: str, password: str) -> bool:
    return await asyncio.to_thread(verify_password, password_hash, password)


@cache
def dummy_hash() -> str:
    """Verified against when the account does not exist, so response time does not reveal it."""
    return hash_password("not-a-real-password")
