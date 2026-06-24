from typing import Literal
from uuid import UUID


from app.models.messages.base import MessageBase, MessagePackType


class Hello(MessageBase):
    type: Literal[MessagePackType.HELLO] = MessagePackType.HELLO
    aid: UUID
    platform: str
