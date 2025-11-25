from fastapi import APIRouter, WebSocket, WebSocketDisconnect
try:
    from backend.connection_manager import manager
except ImportError:
    from connection_manager import manager
import json
import asyncio
import random

router = APIRouter()

@router.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Simulate live updates
            await asyncio.sleep(10) # Update every 10 seconds
            
            # In a real app, we would listen to DB changes or Redis events
            # Here we just send a mock update
            update = {
                "type": "match_update",
                "data": {
                    "match_id": 1, # Mock match ID
                    "home_score": random.randint(0, 5),
                    "away_score": random.randint(0, 5),
                    "minute": random.randint(1, 90)
                }
            }
            await manager.broadcast(json.dumps(update))
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
