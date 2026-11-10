"""Tests for the SQLite file_id cache and rate limiting."""
from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from bot.db.database import Database


@pytest_asyncio.fixture
async def db(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    await database.init()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_cache_miss(db: Database) -> None:
    result = await db.get_cached_file("abc123", "720p")
    assert result is None


@pytest.mark.asyncio
async def test_cache_set_and_get(db: Database) -> None:
    await db.set_cached_file("abc123", "720p", "AgACAgI_file_id_xyz", "video")
    result = await db.get_cached_file("abc123", "720p")
    assert result is not None
    file_id, file_type = result
    assert file_id == "AgACAgI_file_id_xyz"
    assert file_type == "video"


@pytest.mark.asyncio
async def test_cache_different_qualities(db: Database) -> None:
    await db.set_cached_file("abc123", "720p", "file_id_720", "video")
    await db.set_cached_file("abc123", "1080p", "file_id_1080", "video")
    await db.set_cached_file("abc123", "audio", "file_id_audio", "audio")

    r720 = await db.get_cached_file("abc123", "720p")
    r1080 = await db.get_cached_file("abc123", "1080p")
    raudio = await db.get_cached_file("abc123", "audio")

    assert r720 is not None and r720[0] == "file_id_720"
    assert r1080 is not None and r1080[0] == "file_id_1080"
    assert raudio is not None and raudio[0] == "file_id_audio"


@pytest.mark.asyncio
async def test_cache_different_videos(db: Database) -> None:
    await db.set_cached_file("video_a", "720p", "file_a", "video")
    await db.set_cached_file("video_b", "720p", "file_b", "video")

    ra = await db.get_cached_file("video_a", "720p")
    rb = await db.get_cached_file("video_b", "720p")

    assert ra is not None and ra[0] == "file_a"
    assert rb is not None and rb[0] == "file_b"


@pytest.mark.asyncio
async def test_cache_overwrite(db: Database) -> None:
    await db.set_cached_file("abc123", "720p", "old_file_id", "video")
    await db.set_cached_file("abc123", "720p", "new_file_id", "video")
    result = await db.get_cached_file("abc123", "720p")
    assert result is not None
    assert result[0] == "new_file_id"


@pytest.mark.asyncio
async def test_cache_stats_initial(db: Database) -> None:
    stats = await db.get_cache_stats()
    assert stats["total_entries"] == 0
    assert stats["total_requests"] == 0
    assert stats["cache_hits"] == 0
    assert stats["hit_rate_pct"] == 0.0


@pytest.mark.asyncio
async def test_cache_stats_hit_rate(db: Database) -> None:
    await db.set_cached_file("v1", "720p", "fid", "video")
    # 2 requests: 1 hit, 1 miss
    await db.get_cached_file("v1", "720p")   # hit
    await db.get_cached_file("v1", "360p")   # miss
    stats = await db.get_cache_stats()
    assert stats["total_requests"] == 2
    assert stats["cache_hits"] == 1
    assert stats["hit_rate_pct"] == 50.0


@pytest.mark.asyncio
async def test_rate_limit_initial_allowed(db: Database) -> None:
    allowed, msg = await db.check_rate_limit(999, max_jobs=5, max_links=30, window_seconds=600)
    assert allowed is True
    assert msg == ""


@pytest.mark.asyncio
async def test_rate_limit_exceeded(db: Database) -> None:
    # Exhaust 30 requests
    for _ in range(30):
        await db.check_rate_limit(888, max_jobs=5, max_links=30, window_seconds=600)
    # 31st should be denied
    allowed, msg = await db.check_rate_limit(888, max_jobs=5, max_links=30, window_seconds=600)
    assert allowed is False
    assert len(msg) > 0


@pytest.mark.asyncio
async def test_active_jobs_tracking(db: Database) -> None:
    await db.increment_active_jobs(111)
    await db.increment_active_jobs(111)

    allowed, msg = await db.check_rate_limit(111, max_jobs=1, max_links=100, window_seconds=600)
    assert allowed is False

    await db.decrement_active_jobs(111)
    await db.decrement_active_jobs(111)

    allowed, _ = await db.check_rate_limit(111, max_jobs=1, max_links=100, window_seconds=600)
    assert allowed is True


@pytest.mark.asyncio
async def test_decrement_never_goes_negative(db: Database) -> None:
    # Should not raise or go below 0
    await db.decrement_active_jobs(777)
    await db.decrement_active_jobs(777)
