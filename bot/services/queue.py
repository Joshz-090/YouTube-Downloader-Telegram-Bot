from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    UPLOADING = "uploading"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    video_id: str
    quality: str
    user_id: int
    chat_id: int
    status_message_id: int
    job_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: JobStatus = JobStatus.QUEUED
    position: int = 0
    created_at: float = field(default_factory=time.time)


ProcessFn = Callable[[Job], Awaitable[None]]


class DownloadQueue:
    """
    FIFO bounded worker pool.
    - asyncio.Semaphore(max_parallel) limits concurrency.
    - asyncio.Queue provides FIFO ordering.
    - On shutdown, in-flight tasks are cancelled gracefully.
    """

    def __init__(self, max_parallel: int, process_fn: ProcessFn) -> None:
        self._sem = asyncio.Semaphore(max_parallel)
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._active: dict[str, asyncio.Task] = {}
        self._pending: list[Job] = []
        self._process = process_fn
        self._worker_task: asyncio.Task | None = None
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop(), name="queue-worker")
        logger.info("Download queue started")

    async def shutdown(self) -> None:
        """Gracefully stop: cancel in-flight tasks, drain queue."""
        logger.info("Shutting down download queue…")
        self._running = False

        # Cancel pending queue entries
        while not self._queue.empty():
            try:
                job = self._queue.get_nowait()
                job.status = JobStatus.CANCELLED
                logger.info("Cancelled queued job", extra={"job_id": job.job_id})
            except asyncio.QueueEmpty:
                break

        # Cancel active tasks
        for job_id, task in list(self._active.items()):
            if not task.done():
                task.cancel()
                logger.info("Cancelled active job", extra={"job_id": job_id})

        # Wait for them all
        if self._active:
            await asyncio.gather(*self._active.values(), return_exceptions=True)

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        logger.info("Download queue shut down")

    # ── Enqueueing ────────────────────────────────────────────────────────────

    async def enqueue(self, job: Job) -> int:
        """Add a job. Returns 1-based queue position."""
        self._pending.append(job)
        position = len(self._pending)
        job.position = position
        await self._queue.put(job)
        logger.info(
            "Job enqueued",
            extra={"job_id": job.job_id, "user_id": job.user_id, "position": position},
        )
        return position

    async def cancel_user_jobs(self, user_id: int) -> int:
        """Cancel all queued and active jobs for a user. Returns count cancelled."""
        count = 0
        # Mark pending cancelled (they'll be skipped in worker loop)
        for job in self._pending:
            if job.user_id == user_id and job.status == JobStatus.QUEUED:
                job.status = JobStatus.CANCELLED
                count += 1
        return count

    # ── Introspection ──────────────────────────────────────────────────────────

    def queue_length(self) -> int:
        return self._queue.qsize()

    def active_count(self) -> int:
        return len([t for t in self._active.values() if not t.done()])

    def pending_for_user(self, user_id: int) -> int:
        return sum(1 for j in self._pending if j.user_id == user_id and j.status == JobStatus.QUEUED)

    # ── Worker loop ───────────────────────────────────────────────────────────

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if job.status == JobStatus.CANCELLED:
                self._queue.task_done()
                self._remove_pending(job)
                continue

            # Acquire semaphore slot
            await self._sem.acquire()

            task = asyncio.create_task(
                self._run_job(job), name=f"job-{job.job_id}"
            )
            self._active[job.job_id] = task
            self._queue.task_done()

    async def _run_job(self, job: Job) -> None:
        try:
            self._remove_pending(job)
            job.status = JobStatus.DOWNLOADING
            await self._process(job)
            job.status = JobStatus.DONE
        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
            raise
        except Exception as exc:
            job.status = JobStatus.FAILED
            logger.error(
                "Job failed in queue",
                extra={"job_id": job.job_id, "error": str(exc)},
                exc_info=True,
            )
        finally:
            self._active.pop(job.job_id, None)
            self._sem.release()

    def _remove_pending(self, job: Job) -> None:
        try:
            self._pending.remove(job)
        except ValueError:
            pass
