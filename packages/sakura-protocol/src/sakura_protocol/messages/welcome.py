from typing import Literal

from pydantic import BaseModel

from sakura_protocol.messages.base import MessageBase, MessagePackType


class AttachmentAuth(BaseModel):
    type: Literal["bearer"] = "bearer"
    token: str


class AttachmentCapability(BaseModel):
    enabled: bool
    base_url: str
    ttl_seconds: int
    max_size_bytes: int
    hash: Literal["sha256"] = "sha256"
    auth: AttachmentAuth | None = None


class WelcomeCapabilities(BaseModel):
    attachments: AttachmentCapability


class Welcome(MessageBase):
    type: Literal[MessagePackType.WELCOME] = MessagePackType.WELCOME
    core: str = "sakura-core"
    version: str
    capabilities: WelcomeCapabilities
