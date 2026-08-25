"""In-process event bus for live UI updates.

Server-Sent Events rather than WebSockets: every update here travels one way,
server to browser, and SSE gets that with no handshake, no ping/pong and no
reconnect logic of our own -- the browser reconnects by itself.

The bus is per-process and deliberately lossy. It is a notification that
something changed, never a source of truth; clients refetch on receipt. If
the server restarts, nothing important is lost.
"""

import asyncio
import json
from typing import Any

_subscribers: set[asyncio.Queue] = set()


def subscribe() -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    _subscribers.discard(queue)


def publish(event: str, data: dict[str, Any] | None = None) -> None:
    """Fan out an event. Safe to call from sync request handlers.

    A slow client that has filled its queue is skipped rather than allowed to
    block the request that produced the event.
    """
    payload = json.dumps({"event": event, "data": data or {}}, default=str)
    for queue in list(_subscribers):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            continue


def subscriber_count() -> int:
    return len(_subscribers)
