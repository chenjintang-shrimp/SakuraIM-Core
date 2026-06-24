from enum import StrEnum
from typing import Literal
from uuid import UUID


from app.models.messages.base import MessageBase, MessagePackType


class CommandType(StrEnum):
    COMMAND_BIND = "bind"
    COMMAND_DELETE = "delete"
    COMMAND_NEW = "new"
    COMMAND_RESUME = "resume"
    COMMAND_TEMP_SESSION = "temp_session"
    COMMAND_VERIFY = "verify"


class Command(MessageBase):
    type:Literal[MessagePackType.COMMAND] = MessagePackType.COMMAND
    command: CommandType
    args: list[str]
    from_aid: UUID
    sender_pid: str
    seq: int
