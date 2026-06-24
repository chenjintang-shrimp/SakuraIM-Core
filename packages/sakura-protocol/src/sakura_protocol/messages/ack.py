from typing import Literal
from uuid import UUID

from sakura_protocol.messages.base import MessageBase, MessagePackType


class Ack(MessageBase):
    type: Literal[MessagePackType.ACK] = MessagePackType.ACK
    from_aid: UUID
    ack_seq: int
