from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

# ── Patterns ─────────────────────────────────────────────────────────────────

_YT_PATTERNS: list[re.Pattern[str]] = [
    # Standard watch URL
    re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/watch\?(?:.*?[&])?v=([a-zA-Z0-9_-]{11})'),
    # youtu.be short link
    re.compile(r'(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})'),
    # Shorts
    re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})'),
    # Embed
    re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})'),
    # /v/
    re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]{11})'),
]


@dataclass(frozen=True)
class ParsedURL:
    video_id: str
    original_url: str
    is_playlist: bool
    playlist_id: str | None
    timestamp: int | None  # seconds


def parse_youtube_url(url: str) -> ParsedURL | None:
    """
    Parse a YouTube URL and extract video_id, playlist info, and timestamp.
    Returns None if the URL is not a recognized YouTube video URL.
    """
    # Normalize: add scheme if missing so urlparse works
    normalized = url
    if not re.match(r'^https?://', url):
        normalized = 'https://' + url

    # Try each pattern
    video_id: str | None = None
    for pattern in _YT_PATTERNS:
        m = pattern.search(normalized)
        if m:
            video_id = m.group(1)
            break

    if not video_id:
        return None

    # Parse query string for extra info
    parsed = urlparse(normalized)
    qs = parse_qs(parsed.query)

    is_playlist = False
    playlist_id: str | None = None
    if "list" in qs:
        is_playlist = True
        playlist_id = qs["list"][0]

    timestamp: int | None = None
    if "t" in qs:
        try:
            timestamp = int(re.sub(r"[^0-9]", "", qs["t"][0]))
        except (ValueError, IndexError):
            pass
    # Also handle youtu.be?t= in fragment or path
    if timestamp is None and parsed.fragment:
        m = re.search(r't=(\d+)', parsed.fragment)
        if m:
            timestamp = int(m.group(1))

    return ParsedURL(
        video_id=video_id,
        original_url=url,
        is_playlist=is_playlist,
        playlist_id=playlist_id,
        timestamp=timestamp,
    )


def build_clean_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


# ── Format selection ──────────────────────────────────────────────────────────

QUALITY_FORMATS: dict[str, str] = {
    "360p": (
        "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo[height<=360]+bestaudio"
        "/best[height<=360][ext=mp4]"
        "/best[height<=360]"
    ),
    "720p": (
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo[height<=720]+bestaudio"
        "/best[height<=720][ext=mp4]"
        "/best[height<=720]"
    ),
    "1080p": (
        "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo[height<=1080]+bestaudio"
        "/best[height<=1080][ext=mp4]"
        "/best[height<=1080]"
    ),
    "audio": "bestaudio[ext=m4a]/bestaudio[ext=opus]/bestaudio",
}

# Fast progressive (pre-muxed, single stream, no ffmpeg needed)
_FAST_ITAGS: dict[str, str] = {
    "360p": "18",   # 360p H.264+AAC progressive MP4
    "720p": "22",   # 720p H.264+AAC progressive MP4
}


def get_format_string(quality: str, fast: bool = False) -> str:
    """
    Return yt-dlp format string for the requested quality.
    When fast=True, prefer progressive pre-muxed itags first (no ffmpeg needed).
    """
    if quality not in QUALITY_FORMATS:
        raise ValueError(f"Unknown quality: {quality!r}. Must be one of {list(QUALITY_FORMATS)}")
    base = QUALITY_FORMATS[quality]
    if fast and quality in _FAST_ITAGS:
        return f"{_FAST_ITAGS[quality]}/{base}"
    return base


def is_audio_quality(quality: str) -> bool:
    return quality == "audio"
