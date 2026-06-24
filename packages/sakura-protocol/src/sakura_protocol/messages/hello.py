from typing import Literal
from uuid import UUID

from sakura_protocol.messages.base import MessageBase, MessagePackType


class Hello(MessageBase):
    type: Literal[MessagePackType.HELLO] = MessagePackType.HELLO
    aid: UUID
    platform: str
