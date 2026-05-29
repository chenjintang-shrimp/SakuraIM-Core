from __future__ import annotations

from enum import StrEnum

from sqlmodel import Field, SQLModel


class SessionState(StrEnum):
    ESTABLISHED = "established"
    RECONNECTING = "reconnecting"
    ENDED = "ended"


class Session(SQLModel, table=True):
    __tablename__ = "sessions"
    sid: int | None = Field(default=None, primary_key=True, index=True)
    source: int = Field(index=True)
    state: SessionState
    target: int = Field(index=True)

    class Config:
        orm_mode = True
