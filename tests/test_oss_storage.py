import hashlib

import pytest


@pytest.mark.asyncio
async def test_oss_meta_round_trip(tmp_path, monkeypatch):
    db_path = tmp_path / "oss.db"
    object_root = tmp_path / "objects"
    monkeypatch.setenv("OSS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("OSS_OBJECT_ROOT", object_root.as_posix())

    from sakura_oss.db import init_db
    from sakura_oss.storage import get_live_meta, object_path, upsert_meta

    await init_db()
    sha256 = hashlib.sha256(b"hello").hexdigest()
    path = object_path(sha256)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"hello")

    await upsert_meta(sha256, size=5, content_type="text/plain")
    meta = await get_live_meta(sha256)

    assert meta is not None
    assert meta.sha256 == sha256
    assert meta.size == 5


def test_validate_sha256_rejects_bad_values():
    from sakura_oss.storage import validate_sha256

    with pytest.raises(Exception):
        validate_sha256("bad")
