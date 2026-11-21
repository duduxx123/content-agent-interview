import asyncio
import os
import time
from collections.abc import AsyncIterator
from http.cookies import SimpleCookie

import aiohttp
import blivedm
from blivedm.models import web as web_models
from yarl import URL

from content_agent.schemas import LiveEvent


INTERACTION_LABELS = {
    1: "进入直播间",
    2: "关注了主播",
    3: "分享了直播间",
    4: "特别关注了主播",
    5: "互粉了",
    6: "为主播点赞了",
}


class _AgentHandler(blivedm.BaseHandler):
    def __init__(self, queue: asyncio.Queue[LiveEvent], max_queue_size: int) -> None:
        self._queue = queue
        self.dropped_events = 0

    def _push(self, event: LiveEvent) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()
                self.dropped_events += 1
            except asyncio.QueueEmpty:
                pass
        self._queue.put_nowait(event)

    def _on_danmaku(self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage) -> None:
        self._push(LiveEvent(
            kind="danmaku",
            room_id=client.room_id or 0,
            timestamp=message.timestamp // 1000,
            text=message.msg,
            user=message.uname,
        ))

    def _on_gift(self, client: blivedm.BLiveClient, message: web_models.GiftMessage) -> None:
        self._push(LiveEvent(
            kind="gift",
            room_id=client.room_id or 0,
            timestamp=message.timestamp,
            text=f"{message.gift_name} x{message.num}",
            user=message.uname,
            metrics={
                "price": message.price,
                "num": message.num,
                "total_coin": message.total_coin,
                "coin_type": message.coin_type,
            },
        ))

    def _on_gift_v2(
        self, client: blivedm.BLiveClient, message: web_models.SendGiftV2Message
    ) -> None:
        self._push(LiveEvent(
            kind="gift",
            room_id=client.room_id or 0,
            timestamp=message.timestamp or int(time.time()),
            text=f"{message.gift_name or '礼物'} x{message.num or 1}",
            user=message.uname,
            metrics={
                "price": message.price,
                "num": message.num,
                "total_coin": message.total_coin,
                "coin_type": message.coin_type,
            },
        ))

    def _on_buy_guard(self, client: blivedm.BLiveClient, message: web_models.GuardBuyMessage) -> None:
        guard_names = {1: "总督", 2: "提督", 3: "舰长"}
        guard_name = guard_names.get(message.guard_level, "舰队")
        self._push(LiveEvent(
            kind="guard",
            room_id=client.room_id or 0,
            timestamp=message.start_time or int(time.time()),
            text=f"{guard_name} x{message.num}",
            user=message.username,
            metrics={
                "guard_level": message.guard_level,
                "price": message.price,
                "num": message.num,
                "coin_type": "gold",
            },
        ))

    def _on_super_chat(self, client: blivedm.BLiveClient, message: web_models.SuperChatMessage) -> None:
        self._push(LiveEvent(
            kind="super_chat",
            room_id=client.room_id or 0,
            timestamp=message.start_time,
            text=message.message,
            user=message.uname,
            metrics={"price_rmb": message.price},
        ))

    def _on_interact_word_v2(
        self, client: blivedm.BLiveClient, message: web_models.InteractWordV2Message
    ) -> None:
        self._push(LiveEvent(
            kind="room_interaction",
            room_id=client.room_id or 0,
            timestamp=message.timestamp,
            text=INTERACTION_LABELS.get(message.msg_type, "互动"),
            user=message.username,
            metrics={"interaction_type": message.msg_type},
        ))


class BilibiliLiveProvider:
    """接收 B 站网页端直播事件；Cookie 仅保存在当前进程内存中。"""

    def __init__(self, room_id: int, cookie: str, *, max_queue_size: int = 1000) -> None:
        if not cookie.strip():
            raise ValueError("BILIBILI_COOKIE is required")
        self.room_id = room_id
        self._cookie = cookie.strip()
        self._queue: asyncio.Queue[LiveEvent] = asyncio.Queue(maxsize=max_queue_size)
        self._handler = _AgentHandler(self._queue, max_queue_size)
        self._session: aiohttp.ClientSession | None = None
        self._client: blivedm.BLiveClient | None = None

    @classmethod
    def from_env(cls) -> "BilibiliLiveProvider":
        room_id = os.environ.get("BILIBILI_ROOM_ID", "").strip()
        cookie = os.environ.get("BILIBILI_COOKIE", "")
        if not room_id.isdigit():
            raise ValueError("Set BILIBILI_ROOM_ID to the numeric Bilibili room ID")
        return cls(int(room_id), cookie)

    @property
    def dropped_events(self) -> int:
        return self._handler.dropped_events

    async def start(self) -> None:
        if self._client is not None:
            raise RuntimeError("Provider has already been started")
        cookie_jar = aiohttp.CookieJar()
        parsed_cookies = 0
        for pair in self._cookie.split(";"):
            name, separator, value = pair.strip().partition("=")
            if not separator or not name:
                continue
            cookie = SimpleCookie()
            cookie[name] = value.strip()
            cookie[name]["domain"] = ".bilibili.com"
            cookie_jar.update_cookies(cookie, response_url=URL("https://www.bilibili.com"))
            parsed_cookies += 1
        if parsed_cookies == 0:
            raise ValueError("BILIBILI_COOKIE does not contain cookie key/value pairs")

        self._session = aiohttp.ClientSession(cookie_jar=cookie_jar)
        self._client = blivedm.BLiveClient(self.room_id, session=self._session)
        self._client.set_handler(self._handler)
        self._client.start()

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.stop_and_close()
            self._client = None
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def events(self) -> AsyncIterator[LiveEvent]:
        if self._client is None:
            raise RuntimeError("Call start() before consuming events")
        while self._client is not None:
            yield await self.next_event()

    async def next_event(self) -> LiveEvent:
        if self._client is None:
            raise RuntimeError("Call start() before consuming events")
        return await self._queue.get()
