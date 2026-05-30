from dataclasses import dataclass, field
from typing import Sequence
from uuid import UUID

from asq import query
from sqlmodel import select

from app.core.connection_manager import AdapterSession
from app.db import AsyncSessionLocal, get_session
from app.models import Rule, Session, SessionState, User


@dataclass(slots=True)
class GlobalIndexes:
    Sessions: dict[tuple[int, UUID], Session] = field(
        default_factory=dict
    )  # (uid,aid) -> chat session
    Rules: dict[tuple[int, int], Rule] = field(
        default_factory=dict
    )  # (uid,sid) -> rule
    Users: dict[tuple[str, str, UUID], User] = field(
        default_factory=dict
    )  # (pid aka platform_user_id, platform, aid) -> user


async def get_all_users() -> Sequence[User]:
    async with AsyncSessionLocal() as session:
        stmt = select(User)
        users = (await session.exec(stmt)).all()
        return users


async def get_all_active_sessions() -> Sequence[Session]:
    async with AsyncSessionLocal() as session:
        stmt = select(Session).where(Session.state == SessionState.ESTABLISHED)
        active_sessions = (await session.exec(stmt)).all()
        return active_sessions


async def get_all_active_session_rules(active_sid_list: list[int]) -> Sequence[Rule]:
    async with AsyncSessionLocal() as session:
        stmt = select(Rule).where(Rule.belong_sid in active_sid_list)
        active_rules = (await session.exec(stmt)).all()
        return active_rules


async def init_global_indexes() -> GlobalIndexes:
    index = GlobalIndexes()
    all_users = await get_all_users()
    all_active_sessions = await get_all_active_sessions()
    all_active_rules = await get_all_active_session_rules(
        query(list(all_active_sessions))
        .where(lambda s: s.state == SessionState.ESTABLISHED)
        .select(lambda s: s.id)
        .to_list()
    )

    # 我自作自受搞这个数据结构，现在好了，看到三重for循环我就火大
    for user in all_users:
        for platform, pids in user.bind_platform.items():
            for aid, pid in pids:
                index.Users[(pid, platform, aid)] = user

    for current_session in all_active_sessions:
        # 要给每个session标记为RECONNECTING
        current_session.state = SessionState.RECONNECTING
        index.Sessions[(current_session.source, current_session.source_aid)] = (
            current_session
        )
        index.Sessions[(current_session.target, current_session.target_aid)] = (
            current_session
        )

    for rule in all_active_rules:
        index.Rules[(rule.uid_from, rule.belong_sid)] = rule

    return index
