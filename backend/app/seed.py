"""Bootstrap a demo user so the API is usable straight after `uvicorn app.main:app`.

The raw key never touches the database: only its SHA-256 digest is stored.
"""

import asyncio

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, dispose_db, init_db
from app.models import User
from app.security import hash_api_key


async def ensure_seed_user() -> User | None:
    settings = get_settings()
    if not settings.seed_api_key:
        return None

    key_hash = hash_api_key(settings.seed_api_key)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == settings.seed_user_email))
        if user is None:
            user = User(
                email=settings.seed_user_email,
                display_name="Demo User",
                api_key_hash=key_hash,
            )
            session.add(user)
        else:
            user.api_key_hash = key_hash
        await session.commit()
        await session.refresh(user)
        return user


async def _main() -> None:
    await init_db()
    user = await ensure_seed_user()
    if user is None:
        print("SEED_API_KEY is not set - no demo user created.")
    else:
        print(f"Demo user ready: {user.email} (api key taken from SEED_API_KEY)")
    # Without this the aiosqlite worker thread keeps the process alive.
    await dispose_db()


if __name__ == "__main__":
    asyncio.run(_main())
