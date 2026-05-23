"""Bridge between APScheduler (threaded) and the async WebSocket manager.

The scheduler runs on a `BackgroundScheduler` worker thread, so it cannot
directly `await manager.broadcast(...)`. We therefore expose a sync
`enqueue_match_updates` API that pushes payloads onto an in-memory queue,
and a long-running asyncio task (started during FastAPI's lifespan) that
drains the queue and fans out the messages to connected clients.

This keeps the scheduler completely decoupled from the WebSocket runtime
and makes broadcasts best-effort: if the consumer task isn't running yet
(e.g. during startup), updates are buffered in the queue and flushed on
the first tick.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue as thread_queue
from typing import Iterable, List, Mapping, Optional

try:
    from backend.connection_manager import manager
except ImportError:  # script-style execution
    from connection_manager import manager  # type: ignore[no-redef]


logger = logging.getLogger(__name__)


# Cross-thread queue: APScheduler threads put, the asyncio consumer gets.
# Bounded so we never balloon memory if the consumer falls behind for a
# long time (in practice each item is ~150 bytes; 2048 ≈ 300KB).
_UPDATE_QUEUE: "thread_queue.Queue[dict]" = thread_queue.Queue(maxsize=2048)

_consumer_task: Optional[asyncio.Task] = None


def enqueue_match_updates(payloads: Iterable[Mapping[str, object]]) -> None:
    """Submit one or more match updates for broadcast.

    Safe to call from any thread (used by APScheduler jobs). Drops the
    item with a warning if the queue is saturated rather than blocking
    the scheduler thread.
    """
    count = 0
    for payload in payloads:
        message = {
            "type": "match_update",
            "data": dict(payload),
        }
        try:
            _UPDATE_QUEUE.put_nowait(message)
            count += 1
        except thread_queue.Full:
            logger.warning(
                "live_broadcaster queue is full; dropping update for match=%s",
                payload.get("match_id"),
            )
    if count:
        logger.debug("live_broadcaster: enqueued %s payload(s)", count)


async def _consume_loop() -> None:
    """Drain the cross-thread queue and broadcast over WebSocket."""
    loop = asyncio.get_running_loop()
    logger.info("live_broadcaster consumer started")

    while True:
        try:
            # Pull from the threaded queue without blocking the event loop.
            message: dict = await loop.run_in_executor(None, _UPDATE_QUEUE.get)
        except asyncio.CancelledError:
            logger.info("live_broadcaster consumer cancelled")
            raise
        except Exception:
            logger.exception("live_broadcaster: error reading queue")
            await asyncio.sleep(0.5)
            continue

        try:
            await manager.broadcast(json.dumps(message))
        except Exception:
            # Never let a single bad client crash the consumer loop.
            logger.exception(
                "live_broadcaster: broadcast failed for match=%s",
                message.get("data", {}).get("match_id"),
            )


def start_consumer(loop: Optional[asyncio.AbstractEventLoop] = None) -> asyncio.Task:
    """Spawn the consumer task on the given (or current) event loop.

    Idempotent: returns the existing task if one is already running.
    """
    global _consumer_task

    if _consumer_task is not None and not _consumer_task.done():
        return _consumer_task

    target_loop = loop or asyncio.get_event_loop()
    _consumer_task = target_loop.create_task(_consume_loop())
    return _consumer_task


async def stop_consumer() -> None:
    """Cancel the consumer task and drain the queue."""
    global _consumer_task

    if _consumer_task is None:
        return

    _consumer_task.cancel()
    try:
        await _consumer_task
    except (asyncio.CancelledError, Exception):
        pass
    finally:
        _consumer_task = None

    # Drop anything left in the queue — we're shutting down.
    drained = 0
    while True:
        try:
            _UPDATE_QUEUE.get_nowait()
            drained += 1
        except thread_queue.Empty:
            break
    if drained:
        logger.info("live_broadcaster: drained %s pending update(s) on shutdown", drained)
