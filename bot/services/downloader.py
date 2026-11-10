from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import yt_dlp

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[dict], Awaitable[None]]

TWO_GB = 2 * 1024 ** 3  # 2 GB in bytes


class DownloadError(Exception):
    """Raised with a user-friendly (but unescaped) message."""


async def _run_in_executor(fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, *args)


async def _retry(fn, max_attempts: int = 3, base_delay: float = 2.0):
    """Exponential backoff + jitter retry wrapper."""
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except DownloadError:
            raise  # don't retry user errors
        except Exception as exc:
            if attempt == max_attempts:
                raise DownloadError(str(exc)) from exc
            delay = base_delay ** attempt + random.uniform(0, 1)
            logger.warning(
                "Download attempt failed, retrying",
                extra={"attempt": attempt, "delay": delay, "error": str(exc)},
            )
            await asyncio.sleep(delay)


class Downloader:
    def __init__(self, config, db) -> None:
        self._config = config
        self._db = db

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_info(self, url: str) -> dict:
        """Extract video metadata without downloading."""
        opts = {
            "quiet": True,
            "no_warnings": False,
            "skip_download": True,
            "socket_timeout": 30,
        }
        self._apply_auth_opts(opts)

        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            info = await _run_in_executor(_extract)
        except yt_dlp.utils.DownloadError as exc:
            raise DownloadError(str(exc)) from exc
        except Exception as exc:
            raise DownloadError(f"Failed to fetch video info: {exc}") from exc

        if not info:
            raise DownloadError("No info returned by yt-dlp. The URL may be invalid.")

        # Duration check
        duration = info.get("duration")
        if duration and duration > self._config.max_duration:
            raise DownloadError(
                f"too long: video is {duration}s, max allowed is {self._config.max_duration}s"
            )

        return info

    async def download(
        self,
        video_id: str,
        quality: str,
        output_dir: Path,
        on_progress: ProgressCallback,
    ) -> Path:
        """
        Download video/audio to output_dir.
        Returns the Path of the downloaded file.
        Raises DownloadError with a user-friendly message on failure.
        """
        from bot.services.youtube import build_clean_url, get_format_string, is_audio_quality

        url = build_clean_url(video_id)
        fmt = get_format_string(quality, fast=True)
        is_audio = is_audio_quality(quality)

        # We store the actual filepath after yt-dlp resolves the template
        result_path: list[Path] = []
        last_progress_time: list[float] = [0.0]

        def sync_progress_hook(d: dict) -> None:
            # Throttle: only push to async every 0.5s (Telegram throttle is 2s, done in ThrottledEditor)
            now = time.monotonic()
            if now - last_progress_time[0] < 0.5:
                return
            last_progress_time[0] = now
            # Schedule the coroutine on the event loop
            try:
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(on_progress(d))
                )
            except RuntimeError:
                pass

        def _do_download():
            opts = self._make_ydl_opts(
                quality=quality,
                output_dir=output_dir,
                progress_hook=sync_progress_hook,
                is_audio=is_audio,
                fmt=fmt,
            )

            with yt_dlp.YoutubeDL(opts) as ydl:
                # Extract info first to check duration
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise yt_dlp.utils.DownloadError("No info returned")

                duration = info.get("duration")
                if duration and duration > self._config.max_duration:
                    raise yt_dlp.utils.DownloadError(
                        f"too long: {duration}s > {self._config.max_duration}s"
                    )

                # Prepare filename
                filepath = Path(ydl.prepare_filename(info))
                if is_audio:
                    # After extraction the ext will be m4a or mp3
                    filepath = filepath.with_suffix(".m4a")
                else:
                    filepath = filepath.with_suffix(".mp4")
                result_path.append(filepath)

                # Actually download
                ydl.download([url])

            return result_path[0] if result_path else None

        async def attempt():
            path = await _run_in_executor(_do_download)
            return path

        try:
            final_path = await _retry(attempt)
        except DownloadError:
            raise
        except Exception as exc:
            raise DownloadError(str(exc)) from exc

        if final_path is None or not final_path.exists():
            # Try to find any file yt-dlp wrote
            files = list(output_dir.iterdir())
            if files:
                final_path = max(files, key=lambda f: f.stat().st_size)
            else:
                raise DownloadError("Download completed but output file not found.")

        # Size check
        size = final_path.stat().st_size
        if size > TWO_GB:
            final_path.unlink(missing_ok=True)
            raise DownloadError(
                f"too large: file is {size / 1024**3:.1f} GB which exceeds the 2 GB Telegram limit. "
                "Try a lower quality."
            )

        logger.info(
            "Download complete",
            extra={
                "video_id": video_id,
                "quality": quality,
                "size_mb": round(size / 1024**2, 1),
                "path": str(final_path),
            },
        )
        return final_path

    # ── Private helpers ───────────────────────────────────────────────────────

    def _apply_auth_opts(self, opts: dict) -> None:
        if self._config.cookies_path:
            opts["cookiefile"] = str(self._config.cookies_path)
        if self._config.proxy:
            opts["proxy"] = self._config.proxy

    def _make_ydl_opts(
        self,
        quality: str,
        output_dir: Path,
        progress_hook,
        is_audio: bool,
        fmt: str,
    ) -> dict:
        opts: dict = {
            "format": fmt,
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": False,
            "socket_timeout": 30,
            "retries": 10,
            "fragment_retries": 10,
            "file_access_retries": 5,
            "concurrent_fragment_downloads": 8,
            "keepvideo": False,
            "writethumbnail": False,
            "writeinfojson": False,
            "noprogress": False,
            "merge_output_format": "mp4" if not is_audio else None,
        }

        if is_audio:
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "0",
                    "nopostoverwrites": False,
                }
            ]
        else:
            # Remux only — stream copy, never re-encode
            opts["postprocessors"] = [
                {
                    "key": "FFmpegVideoRemuxer",
                    "preferedformat": "mp4",
                }
            ]

        self._apply_auth_opts(opts)
        return opts
