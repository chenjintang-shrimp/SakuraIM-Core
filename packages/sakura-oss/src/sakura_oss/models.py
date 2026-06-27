from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ObjectMeta(SQLModel, table=True):
    __tablename__ = "objects"

    sha256: str = Field(primary_key=True, min_length=64, max_length=64)
    size: int
    content_type: str
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(index=True)
    last_access_at: datetime = Field(default_factory=utc_now)
