from __future__ import annotations

import time

from dataclasses import dataclass, field
from typing import Sequence
from uuid import UUID

from loguru import logger
from sqlalchemy import func
from sqlmodel import select

from sakura_core.db import AsyncSessionLocal
from sakura_core.models import Adapter, Session, SessionState, User


@dataclass(slots=True)
class GlobalIndexes:
    Sessions: dict[tuple[int, UUID], Session] = field(default_factory=dict)
    Sessions_by_sid: dict[int, Session] = field(default_factory=dict)
    Users: dict[tuple[str, str], User] = field(default_factory=dict)
    Usernames: dict[str, User] = field(default_factory=dict)
    Adapters: dict[UUID, str] = field(default_factory=dict)
    Adapters_by_platform: dict[str, list[UUID]] = field(default_factory=dict)
    VerificationCodes: dict[str, tuple[int, str, str, UUID, float]] = field(default_factory=dict)

    def get_session(
        self,
        *,
        sid: int | None = None,
        uid: int | None = None,
        aid: UUID | None = None,
    ) -> Session | list[Session] | None:
        if sid is not None:
            return self.Sessions_by_sid.get(sid)
        elif uid is not None and aid is not None:
            return self.Sessions.get((uid, aid))
        elif uid is not None:
            seen = set()
            result = []
            for session in self.Sessions.values():
                if session.sid is None or session.sid in seen:
                    continue
                if session.source == uid or session.target == uid:
                    seen.add(session.sid)
                    result.append(session)
            return result
        return None

    def get_user(self, pid: str, platform: str) -> User | None:
        return self.Users.get((pid, platform))

    def get_user_by_username(self, username: str) -> User | None:
        return self.Usernames.get(username)

    def get_platform(self, aid: UUID) -> str | None:
        return self.Adapters.get(aid)

    def get_adapters_by_platform(self, platform: str) -> list[UUID]:
        return self.Adapters_by_platform.get(platform, [])

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

    def add_session(self, session: Session) -> None:
        self.Sessions[(session.source, session.source_aid)] = session
        self.Sessions[(session.target, session.target_aid)] = session
        if session.sid is not None:
            self.Sessions_by_sid[session.sid] = session

    def remove_session(self, session: Session) -> None:
        self.Sessions.pop((session.source, session.source_aid), None)
        self.Sessions.pop((session.target, session.target_aid), None)
        if session.sid is not None:
            self.Sessions_by_sid.pop(session.sid, None)

        session.state = SessionState.ENDED

    def update_session_state(self, session: Session, state: SessionState) -> None:
        session.state = state

    def add_user(self, user: User) -> None:
        self.Usernames[user.username] = user
        for platform, pids in user.bind_platform.items():
            for aid, pid in pids:
                self.Users[(pid, platform)] = user

    def remove_user(self, user: User) -> None:
        self.Usernames.pop(user.username, None)
        for platform, pids in user.bind_platform.items():
            for aid, pid in pids:
                self.Users.pop((pid, platform), None)

    def add_adapter(self, aid: UUID, platform: str) -> None:
        self.Adapters[aid] = platform
        self.Adapters_by_platform.setdefault(platform, [])
        if aid not in self.Adapters_by_platform[platform]:
            self.Adapters_by_platform[platform].append(aid)

    def remove_adapter(self, aid: UUID) -> None:
        platform = self.Adapters.pop(aid, None)
        if platform is not None:
            adapters = self.Adapters_by_platform.get(platform, [])
            if aid in adapters:
                adapters.remove(aid)
                if not adapters:
                    self.Adapters_by_platform.pop(platform, None)

    def clear(self) -> None:
        self.Sessions.clear()
        self.Sessions_by_sid.clear()
        self.Users.clear()
        self.Usernames.clear()
        self.Adapters.clear()
        self.Adapters_by_platform.clear()
        self.VerificationCodes.clear()

    def add_verification_code(self, code: str, target_uid: int, requester_pid: str, requester_platform: str, requester_aid: UUID, expiry: float) -> None:
        self.VerificationCodes[code] = (target_uid, requester_pid, requester_platform, requester_aid, expiry)

    def get_verification_code(self, code: str) -> tuple[int, str, str, UUID] | None:
        data = self.VerificationCodes.get(code)
        if data is None:
            return None
        target_uid, requester_pid, requester_platform, requester_aid, expiry = data
        if time.time() > expiry:
            self.VerificationCodes.pop(code, None)
            return None
        self.VerificationCodes.pop(code, None)
        return target_uid, requester_pid, requester_platform, requester_aid


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


async def get_next_sid(db_session) -> int:
    stmt = select(func.max(Session.sid))
    result = await db_session.exec(stmt)
    max_sid = result.one_or_none()
    return (max_sid or 0) + 1


async def get_next_uid(db_session) -> int:
    stmt = select(func.max(User.uid))
    result = await db_session.exec(stmt)
    max_uid = result.one_or_none()
    return (max_uid or 0) + 1


async def init_global_indexes() -> None:
    global _global_indexes

    index = GlobalIndexes()

    async with AsyncSessionLocal() as db_session:
        active_sessions = await _get_all_active_sessions(db_session)
        all_users = await _get_all_users(db_session)
        all_adapters = await _get_all_adapters(db_session)

        for adapter in all_adapters:
            index.Adapters[adapter.aid] = adapter.platform
            index.Adapters_by_platform.setdefault(adapter.platform, [])
            if adapter.aid not in index.Adapters_by_platform[adapter.platform]:
                index.Adapters_by_platform[adapter.platform].append(adapter.aid)

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
            if session.sid is not None:
                index.Sessions_by_sid[session.sid] = session

        await db_session.commit()

    logger.info(
        f"Global indexes initialized: {len(active_sessions)} sessions, "
        f"{len(all_users)} users, {len(all_adapters)} adapters loaded. "
        f"All active sessions marked as RECONNECTING."
    )

    _global_indexes = index