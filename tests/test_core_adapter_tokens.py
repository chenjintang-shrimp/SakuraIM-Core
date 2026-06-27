from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_adapter_token_issue_verify_replace_and_revoke(tmp_path, monkeypatch):
    db_path = tmp_path / "core.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")

    from sakura_core.core.adapter_tokens import (
        issue_adapter_token,
        revoke_adapter_token,
        verify_adapter_token,
    )
    from sakura_core.db import init_db

    await init_db()
    aid = uuid4()

    first = await issue_adapter_token(aid)
    assert await verify_adapter_token(first)

    second = await issue_adapter_token(aid)
    assert await verify_adapter_token(second)
    assert not await verify_adapter_token(first)

    await revoke_adapter_token(aid)
    assert not await verify_adapter_token(second)
