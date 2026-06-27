from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AdapterToken(SQLModel, table=True):
    __tablename__ = "adapter_tokens"

    aid: UUID = Field(primary_key=True)
    token_hash: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=utc_now)
