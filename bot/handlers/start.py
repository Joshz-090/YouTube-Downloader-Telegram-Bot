from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router(name="start")

_START_TEXT = r"""
👋 *Welcome to YT Downloader Bot\!*

⚖️ *Legal Notice*: This bot is for downloading content you _own_, have _explicit permission_ to download, or that is published under *Creative Commons* or *public domain* licenses\. Downloading copyrighted content without permission may violate YouTube's Terms of Service and applicable law\. Use responsibly\.

📖 *Commands:*
/start \- Show this message
/help \- Usage instructions
/cancel \- Cancel your active downloads
/stats \- Bot statistics \(admin only\)

Just send me a YouTube link to get started\! 🎬
""".strip()

_HELP_TEXT = r"""
📖 *How to use:*
1\. Send any YouTube link \(youtu\.be, youtube\.com/watch, /shorts\)
2\. Choose quality: *360p*, *720p*, *1080p*, or *🎵 Audio*
3\. Wait for the download \(progress shown live\)
4\. File delivered to chat\!

⚡ *Tips:*
• Previously downloaded files are cached and sent _instantly_ via Telegram's CDN
• Your queue position is shown when the bot is busy
• Files over 2 GB auto\-fall back to lower quality

🔗 *Supported URL formats:*
• `youtube\.com/watch?v=\.\.\. `
• `youtu\.be/\.\.\.`
• `youtube\.com/shorts/\.\.\.`

⚠️ *Playlists and channels are not supported* — send individual video links only\.
""".strip()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(_START_TEXT, parse_mode="MarkdownV2")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(_HELP_TEXT, parse_mode="MarkdownV2")
