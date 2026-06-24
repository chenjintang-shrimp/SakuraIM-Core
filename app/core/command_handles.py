from __future__ import annotations

import random
import time
from collections.abc import Awaitable, Callable
from uuid import UUID

from asq import query
from loguru import logger

from app.core.connection_manager import manager
from app.core.global_indexes import GlobalIndexes, get_global_indexes, get_next_sid, get_next_uid
from app.db import AsyncSessionLocal
from app.models import Session, SessionState, User
from app.models.messages import Command, CommandType, Info


class UserNotBindInPlatform(Exception):
    pass


def select_adapter_by_platform(
    user: User, platform: str, index: GlobalIndexes
) -> UUID | None:
    # 返回 None 代表找不到合适的adapter跟目标用户对话
    all_bound = user.bind_platform.get(platform)
    if all_bound is None:
        raise UserNotBindInPlatform(
            f"User {user.uid} did not bind on platform {platform}"
        )

    # bind_platform 存储格式: [[aid_str, pid], ...]
    bound_aids = query(all_bound).select(lambda item: UUID(item[0])).to_list()

    sessions = index.get_session(uid=user.uid)
    if sessions is not None:
        used_aids = (
            query(sessions)
            .select(lambda s: s.source_aid if s.source == user.uid else s.target_aid)
            .to_list()
        )

        available = query(bound_aids).where(lambda aid: aid not in used_aids).to_list()

        if not available:
            return None
        return available[0]

    if bound_aids:
        return bound_aids[0]
    return None


async def handle_new_session_create(command: Command) -> bool:
    if command.command != CommandType.COMMAND_NEW:
        return False  # 不应该走到这里
    # New Session Command的args分别是：
    # [0] -> username
    # [1] -> platform

    # 1. 先反查 aid -> platform
    indexs = get_global_indexes()
    platform = indexs.get_platform(command.from_aid)
    if platform is None:
        logger.error(
            f"Adapter {command.from_aid} does not specific its Platform in message type {command.type}. Plz report this bug."
        )
        return False
    # 2. 再查 (pid,platform) -> current_user
    current_user = indexs.get_user(command.sender_pid, platform)
    if current_user is None:
        logger.warning(
            f"User {command.sender_pid} didn't bind adapter {command.from_aid} in platform {platform}."
        )
        await manager.send_to(
            command.from_aid,
            message=Info(
                to_aid=command.from_aid,
                to_pid=command.sender_pid,
                info_type="error",
                body={"error_type": "user_not_bound", "user": f"{command.sender_pid}"},
            ),
        )
        return False

    # 3. 查 username -> target_user
    target_user = indexs.get_user_by_username(command.args[0])
    if target_user is None:
        logger.warning(f"User {command.args[0]} not found.")
        await manager.send_to(
            command.from_aid,
            message=Info(
                to_aid=command.from_aid,
                to_pid=command.sender_pid,
                info_type="error",
                body={"error_type": "user_not_found", "user": f"{command.args[0]}"},
            ),
        )
        return False

    # 4. 选择合适的 adapter
    try:
        aid = select_adapter_by_platform(target_user, command.args[1], indexs)
        if aid is None:
            logger.warning(
                f"User {command.args[0]} on platform {command.args[1]} has no adapters available."
            )
            await manager.send_to(
                command.from_aid,
                message=Info(
                    to_aid=command.from_aid,
                    to_pid=command.sender_pid,
                    info_type="error",
                    body={
                        "error_type": "no_adapter_available",
                        "user": command.args[0],
                        "platform": command.args[1],
                    },
                ),
            )
            return False
        # 5. 创建会话
        async with AsyncSessionLocal() as db_session:
            next_sid = await get_next_sid(db_session)
            new_session = Session(
                sid=next_sid,
                source=current_user.uid,
                source_aid=command.from_aid,
                state=SessionState.ESTABLISHED,
                target=target_user.uid,
                target_aid=aid,
            )
            indexs.add_session(new_session)
            db_session.add(new_session)
            await db_session.commit()

        await manager.send_to(
            command.from_aid,
            message=Info(
                to_aid=command.from_aid,
                to_pid=command.sender_pid,
                info_type="info",
                body={"event": "session_created", "sid": next_sid},
            ),
        )
        return True

    except UserNotBindInPlatform:
        logger.warning(
            f"User {command.args[0]} didn't bind on platform {command.args[1]}."
        )
        await manager.send_to(
            command.from_aid,
            message=Info(
                to_aid=command.from_aid,
                to_pid=command.sender_pid,
                info_type="error",
                body={"error_type": "target_not_bound_on_platform", "user": command.args[0]},
            ),
        )
        return False
    except Exception as e:
        logger.error(f"Exception in handle_new_session_create: {e}")
        return False


async def handle_delete_session(command: Command) -> bool:
    if command.command != CommandType.COMMAND_DELETE:
        return False

    indexs = get_global_indexes()
    platform = indexs.get_platform(command.from_aid)
    if platform is None:
        logger.error(f"Adapter {command.from_aid} platform unknown")
        return False

    current_user = indexs.get_user(command.sender_pid, platform)
    if current_user is None:
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error", body={"error_type": "user_not_bound"}
        ))
        return False

    try:
        sid = int(command.args[0])
    except (IndexError, ValueError):
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error", body={"error_type": "invalid_session_id"}
        ))
        return False

    session = indexs.get_session(sid=sid)
    if session is None or isinstance(session, list):
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error", body={"error_type": "session_not_found"}
        ))
        return False

    if current_user.uid != session.source and current_user.uid != session.target:
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error", body={"error_type": "not_in_session"}
        ))
        return False

    partner_aid = session.target_aid if current_user.uid == session.source else session.source_aid
    partner_uid = session.target if current_user.uid == session.source else session.source

    indexs.remove_session(session)

    async with AsyncSessionLocal() as db_session:
        db_session.add(session)
        await db_session.commit()

    await manager.send_to(partner_aid, message=Info(
        to_aid=partner_aid,
        to_pid=str(partner_uid),
        info_type="info",
        body={"event": "session_ended", "sid": sid}
    ))

    await manager.send_to(command.from_aid, message=Info(
        to_aid=command.from_aid,
        to_pid=command.sender_pid,
        info_type="info",
        body={"event": "session_ended", "sid": sid}
    ))

    return True


async def handle_resume_session(command: Command) -> bool:
    if command.command != CommandType.COMMAND_RESUME:
        return False

    indexs = get_global_indexes()
    platform = indexs.get_platform(command.from_aid)
    if platform is None:
        logger.error(f"Adapter {command.from_aid} platform unknown")
        return False

    current_user = indexs.get_user(command.sender_pid, platform)
    if current_user is None:
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error", body={"error_type": "user_not_bound"}
        ))
        return False

    if not command.args:
        sessions = indexs.get_session(uid=current_user.uid)
        if sessions is None or not isinstance(sessions, list):
            sessions = []
        session_list = [
            {
                "sid": s.sid,
                "partner_uid": s.target if s.source == current_user.uid else s.source,
                "state": s.state,
            }
            for s in sessions
        ]
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="info", body={"sessions": session_list}
        ))
        return True

    try:
        sid = int(command.args[0])
    except ValueError:
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error", body={"error_type": "invalid_session_id"}
        ))
        return False

    session = indexs.get_session(sid=sid)
    if session is None or isinstance(session, list):
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error", body={"error_type": "session_not_found"}
        ))
        return False

    if session.source == current_user.uid:
        # 先从旧索引移除，再更新 aid，再重新加入
        indexs.remove_session(session)
        session.source_aid = command.from_aid
        session.state = SessionState.ESTABLISHED
        indexs.add_session(session)
    elif session.target == current_user.uid:
        indexs.remove_session(session)
        session.target_aid = command.from_aid
        session.state = SessionState.ESTABLISHED
        indexs.add_session(session)
    else:
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error", body={"error_type": "not_in_session"}
        ))
        return False

    async with AsyncSessionLocal() as db_session:
        db_session.add(session)
        await db_session.commit()

    await manager.send_to(command.from_aid, message=Info(
        to_aid=command.from_aid, to_pid=command.sender_pid,
        info_type="info", body={"event": "session_resumed", "sid": sid}
    ))

    return True


async def handle_bind_user(command: Command) -> bool:
    if command.command != CommandType.COMMAND_BIND:
        return False
    # args[0] -> username (要绑定的目标账号名)

    if not command.args:
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error", body={"error_type": "missing_args", "detail": "username required"}
        ))
        return False

    username = command.args[0]
    indexs = get_global_indexes()

    platform = indexs.get_platform(command.from_aid)
    if platform is None:
        logger.error(f"Adapter {command.from_aid} platform unknown")
        return False

    # 检查发起方是否已经绑定了某个账号
    existing_user = indexs.get_user(command.sender_pid, platform)
    if existing_user is not None:
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error",
            body={"error_type": "already_bound", "username": existing_user.username}
        ))
        return False

    # 查找目标 username 是否存在
    target_user = indexs.get_user_by_username(username)

    if target_user is None:
        # 新用户注册：直接创建账号并绑定
        async with AsyncSessionLocal() as db_session:
            next_uid = await get_next_uid(db_session)
            new_user = User(
                uid=next_uid,
                username=username,
                bind_platform={platform: [[str(command.from_aid), command.sender_pid]]},
            )
            db_session.add(new_user)
            await db_session.commit()
            await db_session.refresh(new_user)

        indexs.add_user(new_user)
        logger.info(f"New user registered: {username} (uid={next_uid})")

        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="info",
            body={"event": "bind_success", "username": username, "uid": next_uid}
        ))
        return True

    else:
        # 已存在账号：向目标用户所有在线 Adapter 发验证码
        code = f"{random.randint(0, 999999):06d}"
        expiry = time.time() + 300  # 5分钟

        indexs.add_verification_code(
            code=code,
            target_uid=target_user.uid,
            requester_pid=command.sender_pid,
            requester_platform=platform,
            requester_aid=command.from_aid,
            expiry=expiry,
        )

        # 向目标用户所有平台的所有 Adapter 发验证码通知
        sent_count = 0
        for plat, bindings in target_user.bind_platform.items():
            for binding in bindings:
                aid_str, pid = binding[0], binding[1]
                target_aid = UUID(aid_str)
                ok = await manager.send_to(target_aid, message=Info(
                    to_aid=target_aid,
                    to_pid=pid,
                    info_type="info",
                    body={
                        "event": "bind_request",
                        "code": code,
                        "username": username,
                        "requester_pid": command.sender_pid,
                        "requester_platform": platform,
                        "expires_in": 300,
                    }
                ))
                if ok:
                    sent_count += 1

        if sent_count == 0:
            logger.warning(f"Bind request for {username}: target user has no online adapters")

        # 通知发起方：验证码已发送，等待确认
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="info",
            body={
                "event": "verification_sent",
                "username": username,
                "detail": "A verification code has been sent to the target user. Use 'verify <code>' to confirm.",
            }
        ))
        return True


async def handle_verify(command: Command) -> bool:
    if command.command != CommandType.COMMAND_VERIFY:
        return False
    # args[0] -> verification code

    if not command.args:
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error", body={"error_type": "missing_args", "detail": "code required"}
        ))
        return False

    code = command.args[0]
    indexs = get_global_indexes()

    platform = indexs.get_platform(command.from_aid)
    if platform is None:
        logger.error(f"Adapter {command.from_aid} platform unknown")
        return False

    # verify 必须由已绑定账号的用户发起
    current_user = indexs.get_user(command.sender_pid, platform)
    if current_user is None:
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error", body={"error_type": "user_not_bound"}
        ))
        return False

    # 查验证码
    result = indexs.get_verification_code(code)
    if result is None:
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error", body={"error_type": "invalid_or_expired_code"}
        ))
        return False

    target_uid, requester_pid, requester_platform, requester_aid = result

    # 确认是发给当前用户的验证码
    if target_uid != current_user.uid:
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error", body={"error_type": "code_not_for_you"}
        ))
        return False

    # 将请求方绑定到当前用户账号
    current_user.bind_platform.setdefault(requester_platform, [])
    current_user.bind_platform[requester_platform].append([str(requester_aid), requester_pid])

    # 更新内存索引
    indexs.Users[(requester_pid, requester_platform)] = current_user

    # 写回数据库
    async with AsyncSessionLocal() as db_session:
        db_user = await db_session.get(User, current_user.uid)
        if db_user is not None:
            db_user.bind_platform = current_user.bind_platform
            db_session.add(db_user)
            await db_session.commit()
        else:
            logger.error(f"User {current_user.uid} not found in DB during verify")
            return False

    logger.info(
        f"Bind verified: pid={requester_pid} platform={requester_platform} "
        f"bound to user {current_user.username} (uid={current_user.uid})"
    )

    # 通知请求方绑定成功
    await manager.send_to(requester_aid, message=Info(
        to_aid=requester_aid, to_pid=requester_pid,
        info_type="info",
        body={"event": "bind_success", "username": current_user.username, "uid": current_user.uid}
    ))

    # 通知确认方
    await manager.send_to(command.from_aid, message=Info(
        to_aid=command.from_aid, to_pid=command.sender_pid,
        info_type="info",
        body={"event": "verify_success", "bound_pid": requester_pid, "bound_platform": requester_platform}
    ))

    return True


# 命令分发表
COMMAND_HANDLERS: dict[CommandType, Callable[[Command], Awaitable[bool]]] = {
    CommandType.COMMAND_NEW: handle_new_session_create,
    CommandType.COMMAND_DELETE: handle_delete_session,
    CommandType.COMMAND_RESUME: handle_resume_session,
    CommandType.COMMAND_BIND: handle_bind_user,
    CommandType.COMMAND_VERIFY: handle_verify,
}


async def dispatch_command(command: Command) -> bool:
    handler = COMMAND_HANDLERS.get(command.command)
    if handler is None:
        logger.warning(f"Unsupported command: {command.command}")
        await manager.send_to(command.from_aid, message=Info(
            to_aid=command.from_aid, to_pid=command.sender_pid,
            info_type="error",
            body={"error_type": "unsupported_command", "command": command.command}
        ))
        return False
    return await handler(command)
