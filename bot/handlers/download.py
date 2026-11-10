from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.services.downloader import DownloadError
from bot.services.queue import Job, JobStatus
from bot.utils.formatting import (
    format_file_size,
    format_progress,
    friendly_error,
    is_bot_detection_error,
)

logger = logging.getLogger(__name__)
router = Router(name="download")

# ── Keyboard helpers ──────────────────────────────────────────────────────────

def build_quality_keyboard(video_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📱 360p", callback_data=f"q:{video_id}:360p"),
                InlineKeyboardButton(text="📺 720p", callback_data=f"q:{video_id}:720p"),
                InlineKeyboardButton(text="🖥 1080p", callback_data=f"q:{video_id}:1080p"),
                InlineKeyboardButton(text="🎵 Audio", callback_data=f"q:{video_id}:audio"),
            ]
        ]
    )


# ── Throttled message editor ──────────────────────────────────────────────────

class ThrottledEditor:
    """Edit a Telegram message at most once per 2 seconds."""

    def __init__(self, bot: Bot, chat_id: int, message_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._message_id = message_id
        self._last_edit: float = 0.0
        self._lock = asyncio.Lock()

    async def edit(self, text: str, parse_mode: str = "MarkdownV2") -> None:
        async with self._lock:
            now = time.monotonic()
            if now - self._last_edit < 2.0:
                return
            try:
                await self._bot.edit_message_text(
                    text,
                    chat_id=self._chat_id,
                    message_id=self._message_id,
                    parse_mode=parse_mode,
                )
                self._last_edit = now
            except TelegramBadRequest:
                pass  # "message is not modified" etc.
            except Exception as exc:
                logger.debug("Failed to edit status message", extra={"error": str(exc)})


# ── URL handler ───────────────────────────────────────────────────────────────

_YT_PATTERN = (
    r'(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)'
    r'/(?:watch\?.*?v=|shorts/|embed/|v/)?[a-zA-Z0-9_-]{11}'
)


@router.message(F.text.regexp(_YT_PATTERN))
async def handle_youtube_link(message: Message, bot: Bot) -> None:
    from bot.config import CONFIG
    from bot.db.database import Database
    from bot.services.youtube import parse_youtube_url

    if not message.text or not message.from_user:
        return

    db: Database = bot["db"]

    # Parse URL
    parsed = parse_youtube_url(message.text)
    if not parsed:
        await message.answer(
            "❌ I couldn't parse that YouTube URL\\. Please send a direct video link\\.",
            parse_mode="MarkdownV2",
        )
        return

    # Playlist check
    if parsed.is_playlist and not CONFIG.allow_playlists:
        await message.answer(
            "📋 Playlists are disabled\\.\n\nPlease send a single video URL "
            "\\(remove the `&list=...` part from the URL\\)\\.",
            parse_mode="MarkdownV2",
        )
        return

    # Rate limit check
    allowed, reason = await db.check_rate_limit(
        message.from_user.id,
        max_jobs=5,
        max_links=30,
        window_seconds=600,
    )
    if not allowed:
        await message.answer(reason)
        return

    # Send quality picker
    status_msg = await message.answer(
        "🔗 Link detected\\!\n\nChoose quality \\(auto\\-selects *720p* in 3s\\):",
        reply_markup=build_quality_keyboard(parsed.video_id),
        parse_mode="MarkdownV2",
    )

    # 3-second timeout → auto 720p
    await asyncio.sleep(3.0)

    # Check if still the same message (user may have clicked a button, which edits the message)
    # We detect this by trying to edit; if the keyboard is gone, skip
    try:
        await bot.edit_message_text(
            "⏳ Auto\\-selected *720p*\\. Starting download\\.\\.\\.",
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id,
            parse_mode="MarkdownV2",
        )
    except TelegramBadRequest:
        # Keyboard was already removed by user's choice
        return

    # Trigger 720p download
    await _start_download(
        bot=bot,
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        status_message_id=status_msg.message_id,
        video_id=parsed.video_id,
        quality="720p",
    )


@router.callback_query(F.data.regexp(r'^q:[a-zA-Z0-9_-]{11}:(360p|720p|1080p|audio)$'))
async def handle_quality_choice(callback: CallbackQuery, bot: Bot) -> None:
    from bot.db.database import Database

    if not callback.data or not callback.from_user or not callback.message:
        await callback.answer()
        return

    _, video_id, quality = callback.data.split(":")
    db: Database = bot["db"]

    await callback.answer(f"Starting {quality} download…")

    # Remove the keyboard
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass

    # Check file_id cache first
    cached = await db.get_cached_file(video_id, quality)
    if cached:
        file_id, file_type = cached
        logger.info("Cache hit", extra={"video_id": video_id, "quality": quality, "cache_hit": True})
        try:
            await callback.message.edit_text(
                "✅ Sending cached file instantly\\!",
                parse_mode="MarkdownV2",
            )
        except TelegramBadRequest:
            pass

        await _send_by_file_id(bot, callback.message.chat.id, file_id, file_type, quality)
        return

    # Update status and enqueue
    try:
        await callback.message.edit_text(
            f"⏳ Queuing *{quality}* download\\.\\.\\.",
            parse_mode="MarkdownV2",
        )
    except TelegramBadRequest:
        pass

    await _start_download(
        bot=bot,
        user_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
        status_message_id=callback.message.message_id,
        video_id=video_id,
        quality=quality,
    )


async def _start_download(
    bot: Bot,
    user_id: int,
    chat_id: int,
    status_message_id: int,
    video_id: str,
    quality: str,
) -> None:
    queue = bot["queue"]
    job = Job(
        video_id=video_id,
        quality=quality,
        user_id=user_id,
        chat_id=chat_id,
        status_message_id=status_message_id,
    )
    position = await queue.enqueue(job)
    if position > 1:
        try:
            await bot.edit_message_text(
                f"⏳ *Position in queue: {position}*\n\nYour download will start soon\\.",
                chat_id=chat_id,
                message_id=status_message_id,
                parse_mode="MarkdownV2",
            )
        except TelegramBadRequest:
            pass


async def _send_by_file_id(
    bot: Bot, chat_id: int, file_id: str, file_type: str, quality: str
) -> None:
    try:
        if file_type == "audio":
            await bot.send_audio(chat_id, file_id, caption="🎵 Audio")
        else:
            await bot.send_video(chat_id, file_id, caption=f"📹 {quality}")
    except Exception as exc:
        logger.error("Failed to resend by file_id", extra={"error": str(exc)})
        await bot.send_message(
            chat_id,
            "❌ Failed to resend cached file\\. Please try again\\.",
            parse_mode="MarkdownV2",
        )


# ── Core job processor (called by DownloadQueue) ──────────────────────────────

async def process_download_job(job: Job, bot: Bot, db, downloader) -> None:
    """
    Download and upload a single job. Called by the queue worker.
    - Creates temp dir, downloads, uploads, caches file_id, cleans up.
    """
    from bot.config import CONFIG
    from bot.handlers.admin import send_admin_alert
    from bot.services.youtube import is_audio_quality

    editor = ThrottledEditor(bot, job.chat_id, job.status_message_id)
    await db.increment_active_jobs(job.user_id)

    # Create unique temp dir for this job
    job_tmp = CONFIG.tmp_dir / f"job_{job.job_id}"
    job_tmp.mkdir(parents=True, exist_ok=True)

    try:
        # Progress callback
        async def on_progress(d: dict) -> None:
            status = d.get("status", "")
            if status == "downloading":
                downloaded = d.get("downloaded_bytes", 0) or 0
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                speed = d.get("speed")
                eta = d.get("eta")
                filename = Path(d.get("filename", "")).name
                if total > 0:
                    pct = downloaded / total * 100
                else:
                    pct = 0.0
                text = format_progress(pct, speed, eta, filename)
                await editor.edit(text, parse_mode="MarkdownV2")
            elif status == "finished":
                await editor.edit("📦 Processing\\.\\.\\.", parse_mode="MarkdownV2")

        await editor.edit(f"⬇️ Downloading *{job.quality}*\\.\\.\\.", parse_mode="MarkdownV2")

        # Download
        file_path = await downloader.download(
            video_id=job.video_id,
            quality=job.quality,
            output_dir=job_tmp,
            on_progress=on_progress,
        )

        # Upload
        job.status = JobStatus.UPLOADING
        await editor.edit("📤 Uploading to Telegram\\.\\.\\.", parse_mode="MarkdownV2")

        is_audio = is_audio_quality(job.quality)
        file_size = file_path.stat().st_size
        caption = f"{'🎵' if is_audio else '📹'} {job.quality} • {format_file_size(file_size)}"

        input_file = FSInputFile(file_path, filename=file_path.name)

        if is_audio:
            sent = await bot.send_audio(
                job.chat_id,
                input_file,
                caption=caption,
            )
            file_id = sent.audio.file_id
            file_type = "audio"
        else:
            sent = await bot.send_video(
                job.chat_id,
                input_file,
                caption=caption,
                supports_streaming=True,
            )
            file_id = sent.video.file_id
            file_type = "video"

        # Cache the file_id
        await db.set_cached_file(job.video_id, job.quality, file_id, file_type)
        logger.info(
            "Upload complete, file_id cached",
            extra={
                "video_id": job.video_id,
                "quality": job.quality,
                "file_id": file_id[:20] + "…",
                "cache_hit": False,
            },
        )

        # Clean up status message
        try:
            await bot.delete_message(job.chat_id, job.status_message_id)
        except TelegramBadRequest:
            pass

    except DownloadError as exc:
        err_msg = str(exc)
        logger.warning(
            "Download failed",
            extra={"video_id": job.video_id, "quality": job.quality, "error": err_msg},
        )
        friendly = friendly_error(err_msg)
        try:
            await bot.edit_message_text(
                friendly,
                chat_id=job.chat_id,
                message_id=job.status_message_id,
                parse_mode="MarkdownV2",
            )
        except TelegramBadRequest:
            await bot.send_message(job.chat_id, friendly, parse_mode="MarkdownV2")

        # Bot detection → admin alert
        if is_bot_detection_error(err_msg):
            await send_admin_alert(
                bot,
                CONFIG.admin_id,
                f"⚠️ YouTube bot-detection triggered!\n\nVideo: {job.video_id}\nError: {err_msg[:300]}",
            )

    except asyncio.CancelledError:
        try:
            await bot.edit_message_text(
                "❌ Download cancelled\\.",
                chat_id=job.chat_id,
                message_id=job.status_message_id,
                parse_mode="MarkdownV2",
            )
        except TelegramBadRequest:
            pass
        raise

    except Exception as exc:
        logger.error(
            "Unexpected job error",
            extra={"video_id": job.video_id, "error": str(exc)},
            exc_info=True,
        )
        try:
            await bot.edit_message_text(
                f"❌ An unexpected error occurred\\: `{str(exc)[:100]}`",
                chat_id=job.chat_id,
                message_id=job.status_message_id,
                parse_mode="MarkdownV2",
            )
        except TelegramBadRequest:
            pass

    finally:
        # Always decrement active jobs and clean up temp dir
        await db.decrement_active_jobs(job.user_id)
        import shutil
        try:
            shutil.rmtree(job_tmp, ignore_errors=True)
        except Exception:
            pass


# ── /cancel command ───────────────────────────────────────────────────────────

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, bot: Bot) -> None:
    if not message.from_user:
        return
    queue = bot["queue"]
    count = await queue.cancel_user_jobs(message.from_user.id)
    if count:
        await message.answer(f"✅ Cancelled {count} download(s)\\.", parse_mode="MarkdownV2")
    else:
        await message.answer("ℹ️ No active downloads to cancel\\.", parse_mode="MarkdownV2")
