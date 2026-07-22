import redis.asyncio as aioredis
from sqlalchemy.orm import Session
from fastapi import APIRouter, WebSocket, Query, Depends, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.database import get_db

ws_router = APIRouter()
settings = get_settings()

@ws_router.websocket("/ws/documents")
async def document_status_ws(
    websocket: WebSocket,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    try:
        current_user = get_current_user(token, db)
    except Exception:
        await websocket.close(code = 1008)
        return
    
    if websocket.client_state == WebSocketState.CONNECTING:
        await websocket.accept()

    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis_client.pubsub()
    channel = f"document_status:{current_user.id}"
    await pubsub.subscribe(channel)

    try:
        while websocket.client_state == WebSocketState.CONNECTED:
            mess = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if not mess:
                continue
            if mess.get("type") == "message":
                payload = mess.get("data")
                if isinstance(payload, (bytes, bytearray)):
                    payload = payload.decode()
                if isinstance(payload, str):
                    await websocket.send_text(payload)
    except (RuntimeError, WebSocketDisconnect):
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await redis_client.close()
