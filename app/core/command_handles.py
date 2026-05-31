from __future__ import annotations

from uuid import UUID

from asq import query
from loguru import logger

from app.core.connection_manager import manager
from app.core.global_indexes import GlobalIndexes, get_global_indexes
from app.models import User
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

    bound_aids = (
        query(all_bound)
        .select(lambda item: item[0])
        .to_list()
    )

    sessions = index.get_session(uid=user.uid)
    if sessions is not None:
        used_aids = (
            query(sessions)
            .select(lambda s: s.source_aid if s.source == user.uid else s.target_aid)
            .to_list()
        )

        available = (
            query(bound_aids)
            .where(lambda aid: aid not in used_aids)
            .to_list()
        )

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
            f"User {command.args[0]} didn't bind adapter {command.from_aid} in platform {platform}."
        )
        await manager.send_to(
            command.from_aid,
            message=Info(
                to_aid=command.from_aid,
                to_pid=command.sender_pid,
                type="error",
                body={"error_type": "User Not bind", "user": f"{command.sender_pid}"},
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
                type="error",
                body={"error_type": "User Not bind", "user": f"{command.sender_pid}"},
            ),
        )
        return False

    # 4.选择合适的 adapter
    return True
