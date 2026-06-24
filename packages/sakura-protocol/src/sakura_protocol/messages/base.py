from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class MessagePackType(StrEnum):
    ACK = "ack"
    COMMAND = "command"
    HELLO = "hello"
    INFO = "info"
    MESSAGE = "message"


class MessageBase(BaseModel):
    type: Any
