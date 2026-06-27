from __future__ import annotations

import hashlib
import secrets
from uuid import UUID

from sqlmodel import select

from sakura_core.db import AsyncSessionLocal
from sakura_core.models import AdapterToken


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue_adapter_token(aid: UUID) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)

    async with AsyncSessionLocal() as db_session:
        old = await db_session.get(AdapterToken, aid)
        if old is not None:
            await db_session.delete(old)
        db_session.add(AdapterToken(aid=aid, token_hash=token_hash))
        await db_session.commit()

    return token


async def revoke_adapter_token(aid: UUID) -> None:
    async with AsyncSessionLocal() as db_session:
        token = await db_session.get(AdapterToken, aid)
        if token is not None:
            await db_session.delete(token)
        await db_session.commit()


async def verify_adapter_token(token: str) -> bool:
    token_hash = hash_token(token)
    async with AsyncSessionLocal() as db_session:
        stmt = select(AdapterToken).where(AdapterToken.token_hash == token_hash)
        return (await db_session.exec(stmt)).first() is not None
