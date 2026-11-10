"""Tests for utility formatting functions."""
from __future__ import annotations

from bot.utils.formatting import (
    format_duration,
    format_file_size,
    format_progress,
    friendly_error,
    is_bot_detection_error,
)

# ── format_file_size ──────────────────────────────────────────────────────────

def test_format_file_size_zero() -> None:
    assert format_file_size(0) == "0 B"


def test_format_file_size_bytes() -> None:
    result = format_file_size(500)
    assert "B" in result


def test_format_file_size_kilobytes() -> None:
    assert "KB" in format_file_size(1024)


def test_format_file_size_megabytes() -> None:
    assert "MB" in format_file_size(1024 * 1024)


def test_format_file_size_gigabytes() -> None:
    result = format_file_size(1024 ** 3)
    assert "GB" in result
    assert "1.00" in result


def test_format_file_size_large() -> None:
    result = format_file_size(1.5 * 1024 ** 3)
    assert "1.50 GB" == result


# ── format_duration ───────────────────────────────────────────────────────────

def test_format_duration_zero() -> None:
    assert format_duration(0) == "0s"


def test_format_duration_seconds() -> None:
    assert format_duration(45) == "45s"


def test_format_duration_minutes() -> None:
    assert format_duration(60) == "1m 0s"
    assert format_duration(90) == "1m 30s"


def test_format_duration_hours() -> None:
    assert format_duration(3661) == "1h 1m 1s"
    assert format_duration(7200) == "2h 0m 0s"


# ── format_progress ───────────────────────────────────────────────────────────

def test_format_progress_returns_string() -> None:
    result = format_progress(50.0, 1_000_000, 30, "video.mp4")
    assert isinstance(result, str)
    assert len(result) > 0


def test_format_progress_contains_percent() -> None:
    result = format_progress(75.5, None, None, "")
    assert "75.5" in result


# ── friendly_error ────────────────────────────────────────────────────────────

def test_friendly_error_private() -> None:
    msg = friendly_error("This video is private")
    assert "🔒" in msg or "private" in msg.lower()


def test_friendly_error_age_gated() -> None:
    msg = friendly_error("Sign in to confirm your age")
    assert "🔞" in msg or "age" in msg.lower()


def test_friendly_error_bot_detection() -> None:
    msg = friendly_error("confirm you're not a bot")
    assert "🤖" in msg or "bot" in msg.lower()


def test_friendly_error_geo() -> None:
    msg = friendly_error("not available in your country")
    assert "🌍" in msg or "geo" in msg.lower()


def test_friendly_error_live() -> None:
    msg = friendly_error("This is a live stream and cannot be downloaded")
    assert "📺" in msg or "live" in msg.lower()


def test_friendly_error_live_event() -> None:
    msg = friendly_error("This live event will begin shortly")
    assert "📺" in msg or "live" in msg.lower()


def test_friendly_error_unavailable() -> None:
    msg = friendly_error("Video unavailable")
    assert "❌" in msg or "unavailable" in msg.lower()


def test_friendly_error_fallback() -> None:
    msg = friendly_error("some totally unknown error xyz")
    assert "❌" in msg


# ── is_bot_detection_error ────────────────────────────────────────────────────

def test_is_bot_detection_true() -> None:
    assert is_bot_detection_error("confirm you're not a bot") is True
    assert is_bot_detection_error("Please verify you are not a robot") is True
    assert is_bot_detection_error("Sign in to confirm your identity") is True


def test_is_bot_detection_false() -> None:
    assert is_bot_detection_error("This video is private") is False
    assert is_bot_detection_error("Video unavailable") is False
    assert is_bot_detection_error("") is False
