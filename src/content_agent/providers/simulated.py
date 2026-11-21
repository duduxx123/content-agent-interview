import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from typing import Any

from content_agent.schemas import LiveEvent


class SimulatedLiveProvider:
    """Offline scripted live source, used only for local demos and tests."""

    def __init__(self, interval_seconds: float = 1.5) -> None:
        self._interval = max(0.2, interval_seconds)
        self._queue: asyncio.Queue[LiveEvent] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        script: list[tuple[str, str, dict[str, Any], str]] = [
            ("danmaku", "油皮能用吗？", {}, "观众A"),
            ("danmaku", "有没有小样？", {}, "观众B"),
            (
                "gift",
                "辣条 x10",
                {"price": 100, "num": 10, "total_coin": 1000, "coin_type": "gold"},
                "观众C",
            ),
            ("room_interaction", "进入直播间", {}, "观众D"),
            ("danmaku", "价格太贵了", {}, "观众E"),
            ("super_chat", "敏感肌可以每天用吗？", {"price_rmb": 30}, "观众F"),
            ("danmaku", "666", {}, "观众G"),
            ("danmaku", "什么时候发货？", {}, "观众H"),
            (
                "gift",
                "小心心 x5",
                {"price": 10, "num": 5, "total_coin": 50, "coin_type": "gold"},
                "观众I",
            ),
            (
                "guard",
                "舰长 x1",
                {"guard_level": 3, "price": 198000, "num": 1, "coin_type": "gold"},
                "观众K",
            ),
            (
                "guard",
                "提督 x1",
                {"guard_level": 2, "price": 1998000, "num": 1, "coin_type": "gold"},
                "观众L",
            ),
            ("danmaku", "主播能不能便宜点？", {}, "观众J"),
            ("danmaku", "油皮能用吗？", {}, "观众A"),
        ]
        index = 0
        while self._running:
            kind, text, metrics, user = script[index % len(script)]
            await self._queue.put(
                LiveEvent(
                    kind=kind,
                    room_id=0,
                    timestamp=int(time.time()),
                    text=text,
                    user=user,
                    metrics=metrics,
                )
            )
            index += 1
            await asyncio.sleep(self._interval)

    async def next_event(self) -> LiveEvent:
        return await self._queue.get()

    async def events(self) -> AsyncIterator[LiveEvent]:
        while self._running:
            yield await self.next_event()
