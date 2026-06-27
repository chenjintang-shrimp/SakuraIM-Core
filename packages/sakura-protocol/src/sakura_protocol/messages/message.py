from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import field_validator

from sakura_protocol.messages.base import MessageBase, MessagePackType


class MessageType(StrEnum):
    MESSAGE_NORMAL = "normal"
    MESSAGE_ATTACHMENT = "attachment"
    MESSAGE_REACTION = "reaction"


class Message(MessageBase):
    type: Literal[MessagePackType.MESSAGE] = MessagePackType.MESSAGE
    message_type: MessageType
    sender_aid: UUID
    body: str
    attachments: list[str]
    is_reply: bool
    reply_seq: int
    sender_pid: str

    @field_validator("attachments")
    @classmethod
    def validate_attachments(cls, value: list[str]) -> list[str]:
        for attachment in value:
            if len(attachment) != 64:
                raise ValueError("attachment sha256 must be 64 hex characters")
            try:
                int(attachment, 16)
            except ValueError as exc:
                raise ValueError("attachment sha256 must be hex") from exc
        return value
