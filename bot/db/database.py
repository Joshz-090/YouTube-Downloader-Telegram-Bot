from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

CREATE_FILE_CACHE = """
CREATE TABLE IF NOT EXISTS file_cache (
    video_id    TEXT NOT NULL,
    quality     TEXT NOT NULL,
    file_id     TEXT NOT NULL,
    file_type   TEXT NOT NULL DEFAULT 'video',
    created_at  REAL NOT NULL,
    PRIMARY KEY (video_id, quality)
)
"""

CREATE_RATE_LIMITS = """
CREATE TABLE IF NOT EXISTS rate_limits (
    user_id     INTEGER PRIMARY KEY,
    request_times TEXT NOT NULL DEFAULT '[]',
    active_jobs INTEGER NOT NULL DEFAULT 0
)
"""

CREATE_STATS = """
CREATE TABLE IF NOT EXISTS stats (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
)
"""


class Database:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._total_requests: int = 0
        self._cache_hits: int = 0

    async def init(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.execute("PRAGMA cache_size=-32000")  # 32MB cache
        await self._conn.execute(CREATE_FILE_CACHE)
        await self._conn.execute(CREATE_RATE_LIMITS)
        await self._conn.execute(CREATE_STATS)
        await self._conn.commit()
        logger.info("Database initialized", extra={"path": str(self._path)})

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ── File ID cache ────────────────────────────────────────────────────────

    async def get_cached_file(
        self, video_id: str, quality: str
    ) -> tuple[str, str] | None:
        """Return (file_id, file_type) or None on miss."""
        self._total_requests += 1
        async with self._conn.execute(
            "SELECT file_id, file_type FROM file_cache WHERE video_id=? AND quality=?",
            (video_id, quality),
        ) as cur:
            row = await cur.fetchone()
        if row:
            self._cache_hits += 1
            logger.debug("Cache hit", extra={"video_id": video_id, "quality": quality})
            return row["file_id"], row["file_type"]
        return None

    async def set_cached_file(
        self, video_id: str, quality: str, file_id: str, file_type: str
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO file_cache (video_id, quality, file_id, file_type, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(video_id, quality) DO UPDATE SET
                file_id=excluded.file_id,
                file_type=excluded.file_type,
                created_at=excluded.created_at
            """,
            (video_id, quality, file_id, file_type, time.time()),
        )
        await self._conn.commit()

    async def get_cache_stats(self) -> dict:
        async with self._conn.execute("SELECT COUNT(*) as cnt FROM file_cache") as cur:
            row = await cur.fetchone()
        total_entries = row["cnt"] if row else 0
        hit_rate = (
            round(self._cache_hits / self._total_requests * 100, 1)
            if self._total_requests > 0
            else 0.0
        )
        return {
            "total_entries": total_entries,
            "cache_hits": self._cache_hits,
            "total_requests": self._total_requests,
            "hit_rate_pct": hit_rate,
        }

    # ── Rate limiting ─────────────────────────────────────────────────────────

    async def check_rate_limit(
        self,
        user_id: int,
        max_jobs: int,
        max_links: int,
        window_seconds: int,
    ) -> tuple[bool, str]:
        """
        Returns (allowed, reason_message).
        Increments request count. If over limit returns False.
        """
        now = time.time()
        window_start = now - window_seconds

        # Upsert row
        await self._conn.execute(
            "INSERT OR IGNORE INTO rate_limits (user_id, request_times, active_jobs) VALUES (?, '[]', 0)",
            (user_id,),
        )
        async with self._conn.execute(
            "SELECT request_times, active_jobs FROM rate_limits WHERE user_id=?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()

        times: list[float] = json.loads(row["request_times"])
        active_jobs: int = row["active_jobs"]

        # Prune old entries outside window
        times = [t for t in times if t > window_start]

        # Check active jobs
        if active_jobs >= max_jobs:
            await self._conn.commit()
            return False, f"⚠️ You have {active_jobs} active downloads. Wait for them to finish."

        # Check link rate
        if len(times) >= max_links:
            oldest = times[0]
            reset_in = int(window_start - oldest + window_seconds)
            await self._conn.commit()
            return False, (
                f"⚠️ Rate limit: {max_links} downloads per {window_seconds // 60}min. "
                f"Try again in {reset_in}s."
            )

        # Record this request
        times.append(now)
        await self._conn.execute(
            "UPDATE rate_limits SET request_times=? WHERE user_id=?",
            (json.dumps(times), user_id),
        )
        await self._conn.commit()
        return True, ""

    async def increment_active_jobs(self, user_id: int) -> None:
        await self._conn.execute(
            "INSERT OR IGNORE INTO rate_limits (user_id, request_times, active_jobs) VALUES (?, '[]', 0)",
            (user_id,),
        )
        await self._conn.execute(
            "UPDATE rate_limits SET active_jobs = active_jobs + 1 WHERE user_id=?",
            (user_id,),
        )
        await self._conn.commit()

    async def decrement_active_jobs(self, user_id: int) -> None:
        await self._conn.execute(
            "UPDATE rate_limits SET active_jobs = MAX(0, active_jobs - 1) WHERE user_id=?",
            (user_id,),
        )
        await self._conn.commit()

    async def cleanup_old_rate_data(self) -> None:
        """Prune rate limit timestamps older than 1 hour."""
        cutoff = time.time() - 3600
        async with self._conn.execute("SELECT user_id, request_times FROM rate_limits") as cur:
            rows = await cur.fetchall()
        for row in rows:
            times = [t for t in json.loads(row["request_times"]) if t > cutoff]
            await self._conn.execute(
                "UPDATE rate_limits SET request_times=? WHERE user_id=?",
                (json.dumps(times), row["user_id"]),
            )
        await self._conn.commit()
