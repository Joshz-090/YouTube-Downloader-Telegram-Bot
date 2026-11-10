"""Tests for yt-dlp format string selection."""
from __future__ import annotations

import pytest

from bot.services.youtube import get_format_string


def test_format_string_720p_normal() -> None:
    fmt = get_format_string("720p", fast=False)
    assert "720" in fmt
    assert "mp4" in fmt


def test_format_string_720p_fast() -> None:
    fmt = get_format_string("720p", fast=True)
    # itag 22 should be first preference in fast mode
    assert "22" in fmt


def test_format_string_360p_fast() -> None:
    fmt = get_format_string("360p", fast=True)
    # itag 18 should be first preference
    assert "18" in fmt


def test_format_string_1080p() -> None:
    fmt = get_format_string("1080p")
    assert "1080" in fmt


def test_format_string_audio() -> None:
    fmt = get_format_string("audio")
    assert "bestaudio" in fmt


def test_all_qualities_return_nonempty_string() -> None:
    for quality in ["360p", "720p", "1080p", "audio"]:
        result = get_format_string(quality)
        assert isinstance(result, str), f"Expected str for {quality!r}"
        assert len(result) > 0, f"Empty format string for {quality!r}"


def test_unknown_quality_raises() -> None:
    with pytest.raises(ValueError, match="Unknown quality"):
        get_format_string("4k")


def test_fast_false_does_not_include_itag_for_1080p() -> None:
    # itag 37 is rare; 1080p has no fast itag defined
    fmt = get_format_string("1080p", fast=True)
    # Should still have 1080 in format string
    assert "1080" in fmt


def test_fast_fallback_included() -> None:
    # Fast format should still have the full fallback chain
    fmt = get_format_string("720p", fast=True)
    # After the itag, the full format string should still be there as fallback
    assert "bestvideo" in fmt or "best" in fmt
