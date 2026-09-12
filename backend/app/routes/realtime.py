import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from itsdangerous import TimestampSigner, BadSignature
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import User, UserRole, AccountStatus
from app.services.messaging import owned_conversation
from app.services.realtime import manager, Subscriber
from app.utils.rate_limit import limiter

router = APIRouter()
log = logging.getLogger("platform.websocket")


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_events(socket: WebSocket, conversation_id: int, db: Session = Depends(get_db)):
    if socket.headers.get("origin") not in settings.cors_origins:
        await socket.close(code=1008)
        return
    user_id = socket.session.get("user_id")
    if not user_id:
        await socket.close(code=1008)
        return
    ip = socket.client.host if socket.client else "unknown"
    if limiter.check(("websocket", ip), settings.WS_RATE_LIMIT):
        await socket.close(code=1013)
        return
    try:
        _, issued = TimestampSigner(settings.SECRET_KEY).unsign(socket.cookies.get("session",""),
            max_age=settings.SESSION_MAX_AGE, return_timestamp=True)
        expires = issued.timestamp() + settings.SESSION_MAX_AGE
    except BadSignature:
        await socket.close(code=1008)
        return

    def authorize():
        try:
            if datetime.now(timezone.utc).timestamp() >= expires:
                return False
            db.expire_all()
            user = db.get(User, user_id)
            if not user or user.account_status != AccountStatus.ACTIVE or user.role not in (UserRole.STUDENT, UserRole.ALUMNI):
                return False
            owned_conversation(db, user, conversation_id)
            return True
        except Exception:
            return False
        finally:
            db.rollback()  # Do not hold a database transaction while the socket is idle.

    entry = Subscriber(socket, user_id, conversation_id, authorize)
    if not await run_in_threadpool(authorize):
        await socket.close(code=1008)
        return
    try:
        await socket.accept()
        # Only publish to sockets whose handshake has completed.
        if not manager.add(entry):
            await socket.close(code=1013)
            return
        await entry.deliver({"type":"ready"})
        log.info("connected user_id=%s conversation_id=%s", user_id, conversation_id)
        while True:
            try:
                # Delivery-only protocol: client-supplied send/identity commands are never trusted.
                await asyncio.wait_for(socket.receive_text(), timeout=20)
                await socket.close(code=1008)
                break
            except asyncio.TimeoutError:
                if not await entry.deliver({"type":"heartbeat"}):
                    break
    except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError):
        pass
    finally:
        manager.remove(entry)
        log.info("disconnected user_id=%s conversation_id=%s", user_id, conversation_id)
