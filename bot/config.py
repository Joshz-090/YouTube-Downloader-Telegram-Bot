from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        print(f"[CONFIG ERROR] Required env var '{key}' is missing or empty.", file=sys.stderr)
        print(f"  Copy .env.example → .env and fill in '{key}'.", file=sys.stderr)
        sys.exit(1)
    return val


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _int(key: str, default: int) -> int:
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[CONFIG ERROR] '{key}' must be an integer, got: {raw!r}", file=sys.stderr)
        sys.exit(1)


def _bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    admin_id: int
    api_id: int
    api_hash: str
    local_api_url: str
    cookies_path: Path | None
    proxy: str | None
    max_parallel: int
    max_duration: int
    tmp_dir: Path
    allow_playlists: bool
    log_level: str
    db_path: Path


def load_config() -> Config:
    bot_token = _require("BOT_TOKEN")
    admin_id_str = _require("ADMIN_ID")
    try:
        admin_id = int(admin_id_str)
    except ValueError:
        print(f"[CONFIG ERROR] ADMIN_ID must be an integer, got: {admin_id_str!r}", file=sys.stderr)
        sys.exit(1)

    api_id_str = _require("API_ID")
    try:
        api_id = int(api_id_str)
    except ValueError:
        print(f"[CONFIG ERROR] API_ID must be an integer, got: {api_id_str!r}", file=sys.stderr)
        sys.exit(1)

    api_hash = _require("API_HASH")
    local_api_url = _optional("LOCAL_API_URL", "http://localhost:8081")

    cookies_raw = _optional("COOKIES_PATH")
    cookies_path: Path | None = None
    if cookies_raw:
        p = Path(cookies_raw)
        if not p.exists():
            print(
                f"[CONFIG WARNING] COOKIES_PATH={cookies_raw!r} does not exist. "
                "Proceeding without cookies.",
                file=sys.stderr,
            )
        else:
            cookies_path = p

    proxy_raw = _optional("PROXY")
    proxy: str | None = proxy_raw if proxy_raw else None

    max_parallel = _int("MAX_PARALLEL", 3)
    if max_parallel < 1 or max_parallel > 20:
        print(f"[CONFIG ERROR] MAX_PARALLEL must be 1–20, got {max_parallel}", file=sys.stderr)
        sys.exit(1)

    max_duration = _int("MAX_DURATION", 10800)
    if max_duration < 60:
        print("[CONFIG ERROR] MAX_DURATION must be ≥60 seconds", file=sys.stderr)
        sys.exit(1)

    tmp_dir_raw = _optional("TMP_DIR", "/tmp/ytdlbot")
    tmp_dir = Path(tmp_dir_raw)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    allow_playlists = _bool("ALLOW_PLAYLISTS", False)
    log_level = _optional("LOG_LEVEL", "INFO").upper()
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        log_level = "INFO"

    db_path_raw = _optional("DB_PATH", "data/bot.db")
    db_path = Path(db_path_raw)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Config(
        bot_token=bot_token,
        admin_id=admin_id,
        api_id=api_id,
        api_hash=api_hash,
        local_api_url=local_api_url,
        cookies_path=cookies_path,
        proxy=proxy,
        max_parallel=max_parallel,
        max_duration=max_duration,
        tmp_dir=tmp_dir,
        allow_playlists=allow_playlists,
        log_level=log_level,
        db_path=db_path,
    )


CONFIG = load_config()
