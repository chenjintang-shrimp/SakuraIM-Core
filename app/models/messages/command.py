from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class CommandType(StrEnum):
    COMMAND_BIND = "bind"
    COMMAND_DELETE = "delete"
    COMMAND_NEW = "new"
    COMMAND_RESUME = "resume"
    COMMAND_TEMP_SESSION = "temp_session"


class Command(BaseModel):
    command: CommandType
    args: list[str]
    from_aid: UUID
    sender_pid: str
    seq: int
