from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiofiles
from fastapi import HTTPException, Request
from loguru import logger
from sqlmodel import select

from sakura_oss.configs import get_settings
from sakura_oss.db import AsyncSessionLocal
from sakura_oss.models import ObjectMeta

settings = get_settings()
SHA256_HEX_LENGTH = 64
CHUNK_SIZE = 1024 * 1024


def validate_sha256(sha256: str) -> str:
    if len(sha256) != SHA256_HEX_LENGTH:
        raise HTTPException(status_code=400, detail="invalid sha256")
    try:
        int(sha256, 16)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid sha256") from exc
    return sha256.lower()


def object_path(sha256: str) -> Path:
    root = Path(settings.oss_object_root)
    return root / sha256[:2] / sha256[2:4] / sha256


def temp_path(sha256: str) -> Path:
    return object_path(sha256).with_suffix(".tmp")


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def next_expiry() -> datetime:
    return now_utc() + timedelta(seconds=settings.oss_ttl_seconds)


async def get_live_meta(sha256: str) -> ObjectMeta | None:
    async with AsyncSessionLocal() as db_session:
        meta = await db_session.get(ObjectMeta, sha256)
        if meta is None:
            return None
        path = object_path(sha256)
        if meta.expires_at <= now_utc() or not path.exists():
            await delete_object(sha256)
            return None
        return meta


async def touch_meta(meta: ObjectMeta) -> None:
    async with AsyncSessionLocal() as db_session:
        db_meta = await db_session.get(ObjectMeta, meta.sha256)
        if db_meta is None:
            return
        db_meta.last_access_at = now_utc()
        db_session.add(db_meta)
        await db_session.commit()


async def upsert_meta(sha256: str, size: int, content_type: str) -> ObjectMeta:
    async with AsyncSessionLocal() as db_session:
        meta = await db_session.get(ObjectMeta, sha256)
        if meta is None:
            meta = ObjectMeta(
                sha256=sha256,
                size=size,
                content_type=content_type,
                expires_at=next_expiry(),
            )
        else:
            meta.size = size
            meta.content_type = content_type
            meta.expires_at = next_expiry()
            meta.last_access_at = now_utc()
        db_session.add(meta)
        await db_session.commit()
        await db_session.refresh(meta)
        return meta


async def delete_object(sha256: str) -> None:
    path = object_path(sha256)
    tmp = temp_path(sha256)
    for candidate in (path, tmp):
        try:
            candidate.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(f"failed to delete object file {candidate}: {exc}")
    async with AsyncSessionLocal() as db_session:
        meta = await db_session.get(ObjectMeta, sha256)
        if meta is not None:
            await db_session.delete(meta)
        await db_session.commit()


async def cleanup_expired_once() -> None:
    async with AsyncSessionLocal() as db_session:
        stmt = select(ObjectMeta).where(ObjectMeta.expires_at <= now_utc())
        expired = (await db_session.exec(stmt)).all()

    for meta in expired:
        await delete_object(meta.sha256)

    if expired:
        logger.info(f"cleaned {len(expired)} expired objects")


async def cleanup_loop() -> None:
    while True:
        await asyncio.sleep(settings.oss_cleanup_interval_seconds)
        await cleanup_expired_once()


async def write_request_body(request: Request, sha256: str) -> tuple[int, str]:
    path = object_path(sha256)
    tmp = temp_path(sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0

    try:
        async with aiofiles.open(tmp, "wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > settings.oss_max_size_bytes:
                    raise HTTPException(status_code=413, detail="object too large")
                digest.update(chunk)
                await out.write(chunk)

        actual = digest.hexdigest()
        if actual != sha256:
            raise HTTPException(status_code=422, detail="sha256 mismatch")

        tmp.replace(path)
        return size, actual
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
