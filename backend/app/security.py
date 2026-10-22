"""API key hashing and verification.

Demo-grade: a fast SHA-256 digest of the raw key is enough to avoid storing
usable secrets, and it keeps the dependency list small. Swap in argon2/bcrypt
before running this anywhere that matters.
"""

import hashlib
import hmac

KEY_PREFIX = "pl_"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def keys_match(raw_key: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw_key), stored_hash)


def extract_api_key(header_value: str | None, authorization: str | None) -> str | None:
    if header_value and header_value.strip():
        return header_value.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None
