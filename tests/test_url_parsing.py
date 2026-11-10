"""Tests for YouTube URL parsing."""
from __future__ import annotations

import pytest

from bot.services.youtube import parse_youtube_url


@pytest.mark.parametrize(
    "url, expected_id, expected_playlist, expected_timestamp",
    [
        # Standard watch
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ", False, None),
        # Short URL
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", False, None),
        # Shorts
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ", False, None),
        # Embed
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ", False, None),
        # With timestamp on youtu.be
        ("https://youtu.be/dQw4w9WgXcQ?t=42", "dQw4w9WgXcQ", False, 42),
        # With &t= in full watch URL
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123", "dQw4w9WgXcQ", False, 123),
        # Playlist param → is_playlist=True
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxx", "dQw4w9WgXcQ", True, None),
        # No https
        ("youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ", False, None),
        # With extra params
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share", "dQw4w9WgXcQ", False, None),
        # v/ path
        ("https://www.youtube.com/v/dQw4w9WgXcQ", "dQw4w9WgXcQ", False, None),
        # With si= param (mobile share)
        ("https://youtu.be/dQw4w9WgXcQ?si=abc123", "dQw4w9WgXcQ", False, None),
        # Not YouTube → None
        ("https://vimeo.com/123456789", None, False, None),
        ("https://google.com", None, False, None),
        ("not a url", None, False, None),
        ("https://twitter.com/user/status/123", None, False, None),
    ],
)
def test_parse_youtube_url(
    url: str,
    expected_id: str | None,
    expected_playlist: bool,
    expected_timestamp: int | None,
) -> None:
    result = parse_youtube_url(url)
    if expected_id is None:
        assert result is None, f"Expected None for {url!r}, got {result}"
    else:
        assert result is not None, f"Expected ParsedURL for {url!r}, got None"
        assert result.video_id == expected_id, f"Wrong video_id for {url!r}"
        assert result.is_playlist == expected_playlist, f"Wrong is_playlist for {url!r}"
        assert result.timestamp == expected_timestamp, f"Wrong timestamp for {url!r}"


def test_parse_returns_original_url() -> None:
    url = "https://youtu.be/dQw4w9WgXcQ?t=42"
    result = parse_youtube_url(url)
    assert result is not None
    assert result.original_url == url


def test_parse_playlist_id_extracted() -> None:
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLmyPlaylist123"
    result = parse_youtube_url(url)
    assert result is not None
    assert result.is_playlist is True
    assert result.playlist_id == "PLmyPlaylist123"
