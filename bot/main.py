from __future__ import annotations

import asyncio
import logging
import shutil
import signal
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)


def _sweep_orphans(tmp_dir: Path) -> None:
    """Delete any leftover job_* directories from a previous (crashed) run."""
    if not tmp_dir.exists():
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return
    deleted = 0
    for item in tmp_dir.iterdir():
        if item.name.startswith("job_") and item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
            deleted += 1
    if deleted:
        logger.info("Swept orphan temp directories", extra={"count": deleted})


async def main() -> None:
    from bot.config import CONFIG
    from bot.db.database import Database
    from bot.handlers import admin, download, start
    from bot.handlers.download import process_download_job
    from bot.services.downloader import Downloader
    from bot.services.queue import DownloadQueue
    from bot.services.updater import daily_update_loop
    from bot.utils.logging_setup import setup_logging

    setup_logging(CONFIG.log_level)
    logger.info(
        "Starting YT Downloader Bot",
        extra={
            "max_parallel": CONFIG.max_parallel,
            "max_duration": CONFIG.max_duration,
            "allow_playlists": CONFIG.allow_playlists,
            "local_api_url": CONFIG.local_api_url,
            "cookies": bool(CONFIG.cookies_path),
            "proxy": bool(CONFIG.proxy),
        },
    )

    # Clean up temp dir from previous crash
    _sweep_orphans(CONFIG.tmp_dir)

    # Init database
    db = Database(CONFIG.db_path)
    await db.init()

    # Create Bot session pointed at local API server
    session = AiohttpSession()
    bot = Bot(
        token=CONFIG.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # If using local Bot API server, override the base URL
    if CONFIG.local_api_url and CONFIG.local_api_url != "http://localhost:8081":
        # For non-default local API URLs, set server manually
        from aiogram.client.telegram import TelegramAPIServer
        bot.session.api = TelegramAPIServer(base=CONFIG.local_api_url)
    elif CONFIG.local_api_url:
        from aiogram.client.telegram import TelegramAPIServer
        bot.session.api = TelegramAPIServer(base=CONFIG.local_api_url)

    # Store shared objects in bot's dict for access in handlers
    bot["db"] = db
    bot["config"] = CONFIG

    # Create downloader
    downloader = Downloader(config=CONFIG, db=db)

    # Create process function bound to bot + downloader
    async def process_job(job):
        await process_download_job(job, bot=bot, db=db, downloader=downloader)

    # Create and start queue
    queue = DownloadQueue(max_parallel=CONFIG.max_parallel, process_fn=process_job)
    bot["queue"] = queue
    await queue.start()

    # Create dispatcher and register routers
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(download.router)
    dp.include_router(admin.router)

    # Shutdown flag
    shutdown_event = asyncio.Event()

    def _handle_sigterm(*_):
        logger.info("SIGTERM received, initiating graceful shutdown…")
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_sigterm)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _handle_sigterm)

    # Daily yt-dlp updater (runs async in background)
    async def restart_callback():
        logger.info("yt-dlp updated; signalling restart…")
        # In Docker/systemd restart: unless-stopped handles restart after exit
        shutdown_event.set()

    updater_task = asyncio.create_task(
        daily_update_loop(restart_callback=restart_callback),
        name="ytdlp-updater",
    )

    # Cleanup task for rate limit data
    async def cleanup_loop():
        while not shutdown_event.is_set():
            await asyncio.sleep(3600)
            await db.cleanup_old_rate_data()

    cleanup_task = asyncio.create_task(cleanup_loop(), name="cleanup-loop")

    logger.info("Bot starting, beginning long-poll…")
    try:
        # Start polling in a task so we can also watch shutdown_event
        poll_task = asyncio.create_task(
            dp.start_polling(
                bot,
                allowed_updates=["message", "callback_query"],
            ),
            name="polling",
        )

        # Wait for either polling to end or shutdown signal
        done, pending = await asyncio.wait(
            {poll_task, asyncio.create_task(shutdown_event.wait())},
            return_when=asyncio.FIRST_COMPLETED,
        )

    finally:
        logger.info("Shutting down…")
        updater_task.cancel()
        cleanup_task.cancel()
        await queue.shutdown()
        await db.close()
        await session.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
