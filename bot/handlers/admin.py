from __future__ import annotations

import logging
import shutil
import time

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)
router = Router(name="admin")

_START_TIME = time.time()


async def send_admin_alert(bot: Bot, admin_id: int, text: str) -> None:
    """Send an alert message to the admin. Silently ignore failures."""
    try:
        safe = text.replace("<", "&lt;").replace(">", "&gt;")
        await bot.send_message(admin_id, f"🚨 <b>Admin Alert</b>\n\n{safe}", parse_mode="HTML")
    except Exception as exc:
        logger.error("Failed to send admin alert", extra={"error": str(exc)})


@router.message(Command("stats"))
async def cmd_stats(message: Message, bot: Bot) -> None:
    from bot.config import CONFIG
    from bot.db.database import Database

    # Only admin may use this
    if not message.from_user or message.from_user.id != CONFIG.admin_id:
        await message.answer("⛔ This command is for the bot admin only.")
        return

    # Fetch data injected via middleware
    db: Database = message.bot["db"]
    queue = message.bot["queue"]

    cache_stats = await db.get_cache_stats()

    # Disk usage
    disk = shutil.disk_usage(CONFIG.tmp_dir)
    disk_free_gb = disk.free / 1024**3
    disk_total_gb = disk.total / 1024**3

    # Uptime
    uptime_s = int(time.time() - _START_TIME)
    h, rem = divmod(uptime_s, 3600)
    m, s = divmod(rem, 60)
    uptime_str = f"{h}h {m}m {s}s"

    text = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"🕐 <b>Uptime:</b> {uptime_str}\n"
        f"⬇️ <b>Active downloads:</b> {queue.active_count()}\n"
        f"⏳ <b>Queue length:</b> {queue.queue_length()}\n\n"
        f"💾 <b>Cache entries:</b> {cache_stats['total_entries']}\n"
        f"🎯 <b>Cache hit rate:</b> {cache_stats['hit_rate_pct']}% "
        f"({cache_stats['cache_hits']}/{cache_stats['total_requests']})\n\n"
        f"💿 <b>Disk free:</b> {disk_free_gb:.1f} GB / {disk_total_gb:.1f} GB\n"
        f"📁 <b>Tmp dir:</b> <code>{CONFIG.tmp_dir}</code>"
    )

    await message.answer(text, parse_mode="HTML")
