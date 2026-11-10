from __future__ import annotations

import re


def format_file_size(num_bytes: int | float) -> str:
    """Human-readable file size."""
    if num_bytes == 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.2f} {unit}" if unit != "B" else f"{int(num_bytes)} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def format_duration(seconds: int | float) -> str:
    """Format seconds into human-readable duration."""
    seconds = int(seconds)
    if seconds == 0:
        return "0s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def format_speed(bps: float | None) -> str:
    """Format download speed in bytes/sec."""
    if bps is None or bps <= 0:
        return "—"
    return format_file_size(bps) + "/s"


def format_eta(eta_seconds: float | None) -> str:
    if eta_seconds is None:
        return "—"
    return format_duration(int(eta_seconds))


def format_progress(
    percent: float,
    speed_bps: float | None,
    eta_s: float | None,
    filename: str = "",
) -> str:
    """Build a nice progress string for Telegram messages."""
    filled = int(percent / 5)  # 20 blocks total
    bar = "█" * filled + "░" * (20 - filled)
    lines = [
        "⬇️ Downloading...",
        f"`[{bar}]` {percent:.1f}%",
        f"📶 Speed: `{format_speed(speed_bps)}`  ⏱ ETA: `{format_eta(eta_s)}`",
    ]
    if filename:
        short = filename[:40] + "…" if len(filename) > 40 else filename
        lines.insert(1, f"📄 `{short}`")
    return "\n".join(lines)


# ── Error classification ──────────────────────────────────────────────────────

_BOT_DETECTION_PATTERNS = [
    r"confirm you'?re not a bot",
    r"sign in to confirm",
    r"bot detection",
    r"unusual traffic",
    r"please verify",
    r"captcha",
]

_ERROR_MAP: list[tuple[list[str], str]] = [
    (
        ["private video", "this video is private"],
        "🔒 This video is private and cannot be downloaded.",
    ),
    (
        ["age", "sign in to confirm your age", "age-restricted", "age restricted"],
        "🔞 Age\\-restricted video\\. Try adding cookies from a verified throwaway account\\.",
    ),
    (
        _BOT_DETECTION_PATTERNS,
        "🤖 YouTube bot detection triggered\\. The admin has been alerted\\. Try again later\\.",
    ),
    (
        ["not available in your country", "geo", "geographic", "blocked in your region"],
        "🌍 This video is geo\\-blocked in the server's region\\.",
    ),
    (
        ["live stream", "is live", "live event"],
        "📺 Live streams cannot be downloaded\\. Try after the stream ends\\.",
    ),
    (
        ["playlist", "playlists are not supported"],
        "📋 Playlists are disabled\\. Please send a single video URL\\.",
    ),
    (
        ["too long", "exceeds maximum", "max duration", "duration limit"],
        "⏱ This video exceeds the maximum allowed duration\\.",
    ),
    (
        ["video unavailable", "has been removed", "no longer available"],
        "❌ Video unavailable — it may have been removed or made private\\.",
    ),
    (
        ["copyright", "content warning"],
        "⚠️ This video has content restrictions that prevent downloading\\.",
    ),
]


def friendly_error(msg: str) -> str:
    """Map yt-dlp error strings to user-friendly Telegram messages."""
    lower = msg.lower()
    for patterns, friendly in _ERROR_MAP:
        if any(p.lower() in lower or re.search(p, lower) for p in patterns):
            return friendly
    # Generic fallback — escape for MarkdownV2
    safe = re.sub(r"([_*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", msg[:200])
    return f"❌ Download failed: {safe}"


def is_bot_detection_error(msg: str) -> bool:
    """Return True if the error indicates YouTube bot-detection."""
    lower = msg.lower()
    return any(re.search(p, lower) for p in _BOT_DETECTION_PATTERNS)
