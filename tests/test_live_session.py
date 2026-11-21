import asyncio
import unittest
from collections.abc import AsyncIterator

from content_agent.live_session import LiveSession, LiveSessionError
from content_agent.schemas import (
    LiveConfigUpdate,
    LiveEvent,
    LiveMetricsUpdate,
    LiveStartRequest,
    Product,
)


class FakeProvider:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[LiveEvent] = asyncio.Queue()
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def next_event(self) -> LiveEvent:
        return await self.queue.get()

    async def events(self) -> AsyncIterator[LiveEvent]:
        while True:
            yield await self.next_event()


class LiveSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.provider = FakeProvider()
        self.session = LiveSession(
            window_seconds=3,
            provider_factory=lambda source: self.provider,
        )
        self.queue = self.session.subscribe()

    async def asyncTearDown(self) -> None:
        await self.session.stop()

    async def _wait_for(self, message_type: str, timeout: float = 5.0):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                self.fail(f"timed out waiting for {message_type}")
            message = await asyncio.wait_for(self.queue.get(), remaining)
            if message.get("type") == message_type:
                return message

    async def test_events_stream_and_window_analysis(self) -> None:
        status = await self.session.start(
            LiveStartRequest(
                source="simulated",
                window_seconds=3,
                auto_analyze=True,
            )
        )
        self.assertEqual(status["state"], "listening")
        self.assertTrue(status["auto_analyze"])
        self.assertTrue(self.provider.started)
        self.assertEqual(status["metrics"]["online_count"], 0)
        self.assertEqual(status["metrics"]["cart_click_rate_change"], "")
        self.assertEqual(status["sources"]["conversion_rate"], "unavailable")

        await self.provider.queue.put(
            LiveEvent(
                kind="danmaku",
                room_id=0,
                timestamp=1700000000,
                text="油皮能用吗？",
                user="观众A",
            )
        )
        await self.provider.queue.put(
            LiveEvent(
                kind="gift",
                room_id=0,
                timestamp=1700000001,
                text="辣条 x10",
                metrics={"price": 100},
            )
        )

        event = await self._wait_for("event")
        self.assertEqual(event["event"]["text"], "油皮能用吗？")
        self.assertEqual(event["event"]["user"], "观众A")
        self.assertEqual(event["counts"]["danmaku"], 1)

        analysis = await self._wait_for("analysis", timeout=8.0)
        self.assertTrue(analysis["output"]["suggestions"])
        self.assertEqual(analysis["window_seconds"], 3)
        self.assertIn("油皮能用吗？", analysis["comments"])

        await self.session.stop()
        self.assertTrue(self.provider.stopped)
        self.assertEqual(self.session.status_payload()["state"], "stopped")

    async def test_gift_guard_and_super_chat_totals(self) -> None:
        await self.session.start(
            LiveStartRequest(source="simulated", window_seconds=3)
        )
        events = [
            LiveEvent(
                kind="gift",
                room_id=0,
                timestamp=1700000000,
                text="辣条 x10",
                metrics={
                    "price": 100,
                    "num": 10,
                    "total_coin": 1000,
                    "coin_type": "gold",
                },
            ),
            LiveEvent(
                kind="gift",
                room_id=0,
                timestamp=1700000001,
                text="免费礼物 x1",
                metrics={
                    "price": 0,
                    "num": 1,
                    "total_coin": 1000,
                    "coin_type": "silver",
                },
            ),
            LiveEvent(
                kind="guard",
                room_id=0,
                timestamp=1700000002,
                text="舰长 x1",
                metrics={"guard_level": 3, "price": 198000, "num": 1},
            ),
            LiveEvent(
                kind="guard",
                room_id=0,
                timestamp=1700000003,
                text="提督 x1",
                metrics={"guard_level": 2, "price": 1998000, "num": 1},
            ),
            LiveEvent(
                kind="super_chat",
                room_id=0,
                timestamp=1700000004,
                text="醒目留言",
                metrics={"price_rmb": 30},
            ),
        ]
        for event in events:
            await self.provider.queue.put(event)
        for _ in events:
            await self._wait_for("event")

        totals = self.session.status_payload()["totals"]
        self.assertEqual(totals["gift_items"], 11)
        self.assertEqual(totals["gift_value_rmb"], 1.0)
        self.assertEqual(totals["guard_3_count"], 1)
        self.assertEqual(totals["guard_3_value_rmb"], 198.0)
        self.assertEqual(totals["guard_2_count"], 1)
        self.assertEqual(totals["guard_2_value_rmb"], 1998.0)
        self.assertEqual(totals["super_chat_count"], 1)
        self.assertEqual(totals["super_chat_value_rmb"], 30.0)
        self.assertEqual(totals["total_value_rmb"], 2227.0)

    async def test_runtime_config_updates_product_and_stage(self) -> None:
        await self.session.start(
            LiveStartRequest(source="simulated", window_seconds=3)
        )
        await self.provider.queue.put(
            LiveEvent(
                kind="danmaku",
                room_id=0,
                timestamp=1700000000,
                text="怎么补涂",
            )
        )
        await self._wait_for("event")

        status = self.session.update_config(
            LiveConfigUpdate(
                product=Product(sku_id="20003", name="清透防晒乳"),
                target_stage="促单期",
                elapsed_seconds=3000,
                planned_seconds=3600,
            )
        )
        self.assertEqual(status["target_stage"], "促单期")
        self.assertEqual(status["stage_state"]["current_stage"], "促单期")
        self.assertGreaterEqual(status["elapsed_seconds"], 3000)

        analysis = await self.session.analyze_now()
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis.stage_state.current_stage, "促单期")
        self.assertEqual(analysis.stage_state.source, "directive")
        self.assertTrue(any(item.topic == "用法" for item in analysis.suggestions))

    async def test_auto_analysis_defaults_off(self) -> None:
        status = await self.session.start(
            LiveStartRequest(source="simulated", window_seconds=3)
        )
        self.assertFalse(status["auto_analyze"])

    async def test_auto_analysis_can_be_paused(self) -> None:
        status = await self.session.start(
            LiveStartRequest(
                source="simulated",
                window_seconds=3,
                auto_analyze=False,
            )
        )
        self.assertFalse(status["auto_analyze"])
        await self.provider.queue.put(
            LiveEvent(
                kind="danmaku",
                room_id=0,
                timestamp=1700000000,
                text="油皮能用吗",
            )
        )
        await self._wait_for("event")

        with self.assertRaises(TimeoutError):
            await self._wait_for("analysis", timeout=4.0)

        # Manual analysis still works while automatic windows are paused.
        manual = await self.session.analyze_now()
        self.assertIsNotNone(manual)

        status = self.session.update_config(
            LiveConfigUpdate(auto_analyze=True)
        )
        self.assertTrue(status["auto_analyze"])

    async def test_runtime_config_requires_running_session(self) -> None:
        with self.assertRaises(LiveSessionError):
            self.session.update_config(LiveConfigUpdate(target_stage="促单期"))

    async def test_metrics_push_updates_sources(self) -> None:
        payload = self.session.update_metrics(
            LiveMetricsUpdate(
                online_count=2222,
                cart_click_rate_change="上升12%",
                conversion_rate="3.1%",
                source="external",
            )
        )
        self.assertEqual(payload["metrics"]["online_count"], 2222)
        self.assertEqual(payload["metrics"]["conversion_rate"], "3.1%")
        self.assertEqual(payload["sources"]["online_count"], "external")
        self.assertEqual(payload["sources"]["conversion_rate"], "external")

    async def test_provider_failure_sets_error_status(self) -> None:
        def failing_factory(source: str):
            raise ValueError("BILIBILI_COOKIE is required")

        session = LiveSession(provider_factory=failing_factory)
        with self.assertRaises(LiveSessionError):
            await session.start(LiveStartRequest(source="bilibili"))
        self.assertEqual(session.status_payload()["state"], "error")
        self.assertIn("BILIBILI_COOKIE", session.status_payload()["error"])

    async def test_analyze_now_requires_running_session(self) -> None:
        with self.assertRaises(LiveSessionError):
            await self.session.analyze_now()

    async def test_restart_resets_window_to_default(self) -> None:
        session = LiveSession(
            window_seconds=10,
            provider_factory=lambda source: FakeProvider(),
        )
        await session.start(
            LiveStartRequest(source="simulated", window_seconds=3)
        )
        self.assertEqual(session.status_payload()["window_seconds"], 3)
        await session.stop()
        await session.start(LiveStartRequest(source="simulated"))
        self.assertEqual(session.status_payload()["window_seconds"], 10)
        await session.stop()


if __name__ == "__main__":
    unittest.main()
