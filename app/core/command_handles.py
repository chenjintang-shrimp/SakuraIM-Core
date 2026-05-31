from loguru import logger

from app.core.connection_manager import manager
from app.core.global_indexes import GlobalIndexes, get_global_indexes
from app.models.messages import Command, CommandType, Info


async def handle_new_session_create(command: Command) -> bool:
    if command.command != CommandType.COMMAND_NEW:
        return False  # 不应该走到这里
    # New Session Command的args分别是：
    # [0] -> username
    # [1] -> platform

    # 1. 先反查 aid -> platform
    indexs = get_global_indexes()
    platform = indexs.get_platform(command)
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

    return True
