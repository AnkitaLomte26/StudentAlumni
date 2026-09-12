"""Best-effort delivery only. PostgreSQL and REST history remain authoritative."""
import asyncio
import logging
from dataclasses import dataclass, field
from fastapi.concurrency import run_in_threadpool

log = logging.getLogger("platform.websocket")


@dataclass(eq=False)
class Subscriber:
    websocket: object
    user_id: int
    conversation_id: int
    authorize: object
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def deliver(self, event):
        async with self.lock:
            if not await run_in_threadpool(self.authorize):
                await self.websocket.close(code=1008)
                return False
            await asyncio.wait_for(self.websocket.send_json(event), timeout=3)
            return True


class ConnectionManager:
    def __init__(self):
        self.subscribers = set()

    def add(self, entry):
        if len(self.subscribers) >= 1000 or sum(s.user_id == entry.user_id for s in self.subscribers) >= 5:
            return False
        self.subscribers.add(entry)
        return True

    def remove(self, entry):
        self.subscribers.discard(entry)

    async def publish(self, conversation_id, message):
        targets = [s for s in self.subscribers if s.conversation_id == conversation_id]
        async def deliver(entry):
            try:
                if not await entry.deliver({"type":"message.created", "message":message}):
                    self.remove(entry)
            except Exception:
                self.remove(entry)
                try:
                    await entry.websocket.close(code=1013)
                except Exception:
                    pass
                log.info("delivery_unavailable conversation_id=%s user_id=%s", conversation_id, entry.user_id)
        await asyncio.gather(*(deliver(s) for s in targets))

    async def close_user(self, user_id=None):
        for entry in list(self.subscribers):
            if user_id is None or entry.user_id == user_id:
                self.remove(entry)
                try:
                    async with entry.lock:
                        await entry.websocket.close(code=1008 if user_id is not None else 1001)
                except Exception:
                    pass

manager = ConnectionManager()

