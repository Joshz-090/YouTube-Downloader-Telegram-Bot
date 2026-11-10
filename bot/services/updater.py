from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


async def update_ytdlp() -> str:
    """
    Upgrade yt-dlp via pip in a subprocess.
    Runs in a thread so it doesn't block the event loop.
    Returns combined stdout+stderr output.
    """

    def _run() -> str:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            raise RuntimeError(f"pip upgrade failed (rc={result.returncode}):\n{output[:500]}")
        return output

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run)


async def daily_update_loop(
    restart_callback: Callable[[], Awaitable[None]] | None = None,
    interval_seconds: int = 86400,
) -> None:
    """
    Runs every `interval_seconds` (default 24h):
    1. Updates yt-dlp via pip.
    2. Calls restart_callback if provided (e.g. to signal the process to restart).

    Exceptions are caught and logged; the loop continues regardless.
    """
    logger.info(
        "Daily yt-dlp updater started",
        extra={"interval_seconds": interval_seconds},
    )
    while True:
        await asyncio.sleep(interval_seconds)
        logger.info("Running scheduled yt-dlp update…")
        try:
            output = await update_ytdlp()
            logger.info(
                "yt-dlp update succeeded",
                extra={"output_preview": output[:300]},
            )
            if restart_callback is not None:
                await restart_callback()
        except Exception as exc:
            logger.error(
                "yt-dlp update failed",
                extra={"error": str(exc)},
                exc_info=True,
            )
