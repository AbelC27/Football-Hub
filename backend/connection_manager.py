from typing import List
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        # Iterate over a snapshot so a disconnect mid-broadcast can't trip
        # the loop on a mutated list.
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                # Drop dead connections so they don't accumulate.
                self.disconnect(connection)

    async def shutdown(self):
        for connection in list(self.active_connections):
            try:
                await connection.close(code=1001)  # 1001 = going away
            except Exception:
                pass
            self.disconnect(connection)

manager = ConnectionManager()





