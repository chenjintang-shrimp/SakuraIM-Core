from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"
    uid: int = Field(primary_key=True, index=True)
    username: str = Field(index=True)
    # 存储格式: {platform: [[aid_str, pid], ...]}
    # 用 JSON 序列化，UUID 以字符串形式存储
    bind_platform: dict[str, list[list[str]]] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
