import asyncio
import time
import json
import logging
from typing import Dict, Any, Set, Optional

logger = logging.getLogger("lgp.event_bus")

class GlobalEventBus:
    """Singleton event bus for distributing real-time updates across LGP v2.0 components and Dashboard SSE."""
    _instance: Optional["GlobalEventBus"] = None

    def __init__(self):
        self._listeners: Set[asyncio.Queue] = set()

    @classmethod
    def get_instance(cls) -> "GlobalEventBus":
        if cls._instance is None:
            cls._instance = GlobalEventBus()
        return cls._instance

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=200)
        self._listeners.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._listeners.discard(q)

    def publish_sync(self, event_type: str, data: Dict[str, Any]):
        """Publish event safely without awaiting (for synchronous or fire-and-forget contexts)."""
        evt = {
            "event": event_type,
            "data": data,
            "timestamp": time.time()
        }
        dead_queues = []
        for q in list(self._listeners):
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                dead_queues.append(q)
            except Exception:
                pass
        for dq in dead_queues:
            self._listeners.discard(dq)

    async def publish(self, event_type: str, data: Dict[str, Any]):
        """Publish event asynchronously to all active SSE queues."""
        self.publish_sync(event_type, data)

        # If running in external CLI or process, also attempt non-blocking HTTP dispatch
        try:
            import httpx
            # Only send if running standalone and port 8000 is open
            async with httpx.AsyncClient(timeout=0.3) as client:
                await client.post(
                    "http://localhost:8000/api/events/broadcast",
                    json={"event": event_type, "data": data}
                )
        except Exception:
            pass  # Local process already got it via memory or server is self
