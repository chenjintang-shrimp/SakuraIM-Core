import uuid
from uuid import UUID

from sqlmodel import Field, SQLModel


class Adapter(SQLModel, table=True):
    __tablename__ = "adapters"

    aid: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    platform: str
