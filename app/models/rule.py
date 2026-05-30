from __future__ import annotations

from sqlmodel import Field, SQLModel


class Rule(SQLModel, table=True):
    __tablename__ = "rules"
    rid: int | None = Field(default=None, primary_key=True, index=True)
    belong_sid: int
    uid_from: int
    pid_to: int
    aid_to: int
