from uuid import UUID

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"
    uid: int = Field(primary_key=True, index=True)
    username: str = Field(index=True)
    bind_platform: dict[str, list[tuple[UUID, str]]]
