from typing import Literal
from uuid import UUID


from app.models.messages.base import MessageBase, MessagePackType


class Ack(MessageBase):
    type: Literal[MessagePackType.ACK] = MessagePackType.ACK
    from_aid: UUID
    ack_seq: int
