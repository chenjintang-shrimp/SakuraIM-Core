from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Sequence
from uuid import UUID

from loguru import logger
from sqlmodel import select

from app.db import AsyncSessionLocal
from app.models import Adapter, Session, SessionState, User


@dataclass(slots=True)
class GlobalIndexes:
    Sessions: dict[tuple[int, UUID], Session] = field(default_factory=dict)
    Users: dict[tuple[str, str], User] = field(default_factory=dict)
    Usernames: dict[str, User] = field(default_factory=dict)
    Adapters: dict[UUID, str] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def get_session(self, uid: int, aid: UUID) -> Session | None:
        return self.Sessions.get((uid, aid))

    def get_user(self, pid: str, platform: str) -> User | None:
        return self.Users.get((pid, platform))

    def get_user_by_username(self, username: str) -> User | None:
        return self.Usernames.get(username)

    def get_platform(self, aid: UUID) -> str | None:
        return self.Adapters.get(aid)

    def get_target(self, sender_uid: int, sender_aid: UUID) -> tuple[int, UUID] | None:
        session = self.Sessions.get((sender_uid, sender_aid))
        if session is None:
            return None

        if session.source == sender_uid and session.source_aid == sender_aid:
            return session.target, session.target_aid
        if session.target == sender_uid and session.target_aid == sender_aid:
            return session.source, session.source_aid

        logger.warning(
            f"Session {session.sid} inconsistent: sender ({sender_uid}, {sender_aid}) not found in either side"
        )
        return None

    async def add_session(self, session: Session) -> None:
        async with self._lock:
            self.Sessions[(session.source, session.source_aid)] = session
            self.Sessions[(session.target, session.target_aid)] = session

    async def remove_session(self, session: Session) -> None:
        async with self._lock:
            self.Sessions.pop((session.source, session.source_aid), None)
            self.Sessions.pop((session.target, session.target_aid), None)

        session.state = SessionState.ENDED

    async def update_session_state(self, session: Session, state: SessionState) -> None:
        session.state = state

    async def add_user(self, user: User) -> None:
        async with self._lock:
            self.Usernames[user.username] = user
            for platform, pids in user.bind_platform.items():
                for aid, pid in pids:
                    self.Users[(pid, platform)] = user

    async def remove_user(self, user: User) -> None:
        async with self._lock:
            self.Usernames.pop(user.username, None)
            for platform, pids in user.bind_platform.items():
                for aid, pid in pids:
                    self.Users.pop((pid, platform), None)

    async def add_adapter(self, aid: UUID, platform: str) -> None:
        async with self._lock:
            self.Adapters[aid] = platform

    async def remove_adapter(self, aid: UUID) -> None:
        async with self._lock:
            self.Adapters.pop(aid, None)

    async def clear(self) -> None:
        async with self._lock:
            self.Sessions.clear()
            self.Users.clear()
            self.Usernames.clear()
            self.Adapters.clear()


_global_indexes: GlobalIndexes | None = None


def get_global_indexes() -> GlobalIndexes:
    if _global_indexes is None:
        raise RuntimeError(
            "Global indexes not initialized. "
            "Ensure init_global_indexes() is called during application startup."
        )
    return _global_indexes


async def _get_all_users(db_session) -> Sequence[User]:
    stmt = select(User)
    return (await db_session.exec(stmt)).all()


async def _get_all_active_sessions(db_session) -> Sequence[Session]:
    stmt = select(Session).where(Session.state != SessionState.ENDED)
    return (await db_session.exec(stmt)).all()


async def _get_all_adapters(db_session) -> Sequence[Adapter]:
    stmt = select(Adapter)
    return (await db_session.exec(stmt)).all()


async def init_global_indexes() -> None:
    global _global_indexes

    index = GlobalIndexes()

    async with AsyncSessionLocal() as db_session:
        active_sessions = await _get_all_active_sessions(db_session)
        all_users = await _get_all_users(db_session)
        all_adapters = await _get_all_adapters(db_session)

        for adapter in all_adapters:
            index.Adapters[adapter.aid] = adapter.platform

        for user in all_users:
            index.Usernames[user.username] = user
            for platform, pids in user.bind_platform.items():
                for aid, pid in pids:
                    index.Users[(pid, platform)] = user

        for session in active_sessions:
            session.state = SessionState.RECONNECTING
            db_session.add(session)
            index.Sessions[(session.source, session.source_aid)] = session
            index.Sessions[(session.target, session.target_aid)] = session

        await db_session.commit()

    logger.info(
        f"Global indexes initialized: {len(active_sessions)} sessions, "
        f"{len(all_users)} users, {len(all_adapters)} adapters loaded. "
        f"All active sessions marked as RECONNECTING."
    )

    _global_indexes = index