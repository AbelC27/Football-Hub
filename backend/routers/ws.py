"""WebSocket router for live match updates.

Clients open a single connection to `/ws/live` and receive JSON payloads
of the form:

    {
        "type": "match_update",
        "data": {
            "match_id": <int>,
            "status": <str>,           # NS / LIVE / HT / FT / ...
            "home_score": <int|null>,
            "away_score": <int|null>,
            "current_minute": <int|null>
        }
    }

The actual fan-out is driven by `services.live_broadcaster`, which
consumes updates emitted by APScheduler jobs after each provider sync.
This handler is intentionally minimal: accept the connection, keep it
open, and let the broadcaster push messages.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

try:
    from backend.connection_manager import manager
except ImportError:
    from connection_manager import manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # We don't expect inbound traffic on this channel today, but we
        # still need to await something so the connection stays open.
        # `receive_text()` raises WebSocketDisconnect on close, which is
        # exactly the signal we want.
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                raise
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error on /ws/live receive loop")
                break
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
