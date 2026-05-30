from uuid import UUID

from pydantic import BaseModel


class Ack(BaseModel):
    from_aid: UUID
    ack_seq: int