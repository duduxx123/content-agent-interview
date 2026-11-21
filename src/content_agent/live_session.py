import asyncio
import contextlib
import json
import logging
import time
from collections import Counter, deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

import aiohttp
from starlette.requests import Request

from content_agent.modules.live_structure import LiveStructureModule
from content_agent.pipeline import analyze_async
from content_agent.providers.base import LiveDataProvider
from content_agent.providers.bilibili import BilibiliLiveProvider
from content_agent.providers.simulated import SimulatedLiveProvider
from content_agent.schemas import (
    AgentInput,
    AgentOutput,
    BackendMetrics,
    CommentAnalysis,
    LiveConfigUpdate,
    LiveEvent,
    LiveMetricsUpdate,
    LiveStartRequest,
    LiveState,
    StageDirective,
)


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = PROJECT_ROOT / "examples" / "scene.json"
ROOM_INFO_URL = "https://api.live.bilibili.com/room/v1/Room/get_info"
ROOM_INFO_INTERVAL_SECONDS = 20
IDLE_STOP_SECONDS = 60


class LiveSessionError(RuntimeError):
    """Raised when a live session cannot start or is not running."""


def _sse(event_name: str, payload: dict[str, Any]) -> str:
    return (
        f"event: {event_name}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


class LiveSession:
    """Consume a live provider, broadcast events over SSE, and analyze time windows."""

    def __init__(
        self,
        template_path: str | Path = DEFAULT_TEMPLATE,
        *,
        window_seconds: int = 10,
        max_events: int = 300,
        provider_factory: Callable[[str], LiveDataProvider] | None = None,
    ) -> None:
        self._template = AgentInput.model_validate_json(
            Path(template_path).read_text(encoding="utf-8-sig")
        )
        self._default_window_seconds = max(3, window_seconds)
        self._window_seconds = self._default_window_seconds
        self._max_events = max_events
        self._provider_factory = provider_factory or self._default_provider
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._counts: Counter[str] = Counter()
        self._window_counts: Counter[str] = Counter()
        self._window_comments: list[str] = []

        self._analysis: AgentOutput | None = None
        self._last_analysis_at: int | None = None
        self._status = "idle"
        self._error: str | None = None
        self._source = "bilibili"
        self._room_id: int | None = None
        self._running = False
        self._provider: LiveDataProvider | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._idle_task: asyncio.Task[None] | None = None
        self._started_at: int | None = None
        self._started_monotonic: float | None = None
        self._start_elapsed = self._template.live_state.elapsed_seconds
        self._planned_seconds = self._template.live_state.planned_seconds
        self._current_stage = self._template.live_state.current_stage
        self._directive: StageDirective | None = None
        self._product = self._template.product
        self._backend_metrics = BackendMetrics(online_count=0)
        self._metrics_sources = {
            "online_count": "pending",
            "cart_click_rate_change": "unavailable",
            "conversion_rate": "unavailable",
        }
        self._totals = self._empty_totals()
        self._auto_analyze = False
        self._seq = 0

        self._stage_engine = LiveStructureModule()
        self._lifecycle_lock = asyncio.Lock()
        self._analysis_lock = asyncio.Lock()

    def _default_provider(self, source: str) -> LiveDataProvider:
        if source == "simulated":
            return SimulatedLiveProvider()
        return BilibiliLiveProvider.from_env()

    @property
    def running(self) -> bool:
        return self._running

    def _current_elapsed(self) -> int:
        elapsed = self._start_elapsed
        if self._started_monotonic is not None:
            elapsed += int(time.monotonic() - self._started_monotonic)
        return elapsed

    def stage_state_payload(self) -> dict[str, Any]:
        state = LiveState(
            current_stage=self._current_stage,
            elapsed_seconds=self._current_elapsed(),
            planned_seconds=self._planned_seconds,
            current_sku=self._product.sku_id,
        )
        return self._stage_engine.evaluate(state, self._directive).model_dump()

    @staticmethod
    def _empty_totals() -> dict[str, float | int]:
        return {
            "gift_items": 0,
            "gift_value_rmb": 0.0,
            "super_chat_count": 0,
            "super_chat_value_rmb": 0.0,
            "guard_3_count": 0,
            "guard_3_value_rmb": 0.0,
            "guard_2_count": 0,
            "guard_2_value_rmb": 0.0,
            "guard_1_count": 0,
            "guard_1_value_rmb": 0.0,
            "total_value_rmb": 0.0,
        }

    @staticmethod
    def _as_number(value: Any, default: float = 0.0) -> float:
        try:
            if isinstance(value, bool):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _event_value_rmb(self, event: LiveEvent) -> float:
        """Convert gold seeds to CNY; silver gifts have no face value."""
        metrics = event.metrics
        if event.kind == "super_chat":
            return max(0.0, self._as_number(metrics.get("price_rmb")))
        if event.kind == "guard":
            price = self._as_number(metrics.get("price"))
            num = self._as_number(metrics.get("num"), 1.0) or 1.0
            return max(0.0, price * num / 1000)
        if event.kind == "gift":
            if str(metrics.get("coin_type") or "gold").casefold() == "silver":
                return 0.0
            total_coin = self._as_number(metrics.get("total_coin"))
            if total_coin > 0:
                return total_coin / 1000
            price = self._as_number(metrics.get("price"))
            num = self._as_number(metrics.get("num"), 1.0) or 1.0
            return max(0.0, price * num / 1000)
        return 0.0

    def _accumulate_totals(self, event: LiveEvent, value_rmb: float) -> None:
        totals = self._totals
        if event.kind == "gift":
            items = self._as_number(event.metrics.get("num"), 1.0) or 1.0
            totals["gift_items"] += int(items)
            totals["gift_value_rmb"] += value_rmb
        elif event.kind == "guard":
            level = int(self._as_number(event.metrics.get("guard_level")))
            if level in {1, 2, 3}:
                items = self._as_number(event.metrics.get("num"), 1.0) or 1.0
                totals[f"guard_{level}_count"] += int(items)
                totals[f"guard_{level}_value_rmb"] += value_rmb
        elif event.kind == "super_chat":
            totals["super_chat_count"] += 1
            totals["super_chat_value_rmb"] += value_rmb
        if event.kind in {"gift", "guard", "super_chat"}:
            totals["total_value_rmb"] += value_rmb

    def totals_payload(self) -> dict[str, Any]:
        result = dict(self._totals)
        for key in list(result):
            if key.endswith("_rmb"):
                result[key] = round(float(result[key]), 2)
        return result

    def status_payload(self) -> dict[str, Any]:
        return {
            "state": self._status,
            "source": self._source,
            "room_id": self._room_id,
            "window_seconds": self._window_seconds,
            "started_at": self._started_at,
            "elapsed_seconds": self._current_elapsed(),
            "planned_seconds": self._planned_seconds,
            "current_stage": self._current_stage,
            "target_stage": self._directive.target_stage if self._directive else None,
            "auto_analyze": self._auto_analyze,
            "stage_state": self.stage_state_payload(),
            "event_count": sum(self._counts.values()),
            "counts": dict(self._counts),
            "subscribers": len(self._subscribers),
            "last_analysis_at": self._last_analysis_at,
            "error": self._error,
            "totals": self.totals_payload(),
            **self.metrics_payload(),
        }

    def metrics_payload(self) -> dict[str, Any]:
        return {
            "metrics": self._backend_metrics.model_dump(),
            "sources": dict(self._metrics_sources),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "type": "snapshot",
            "status": self.status_payload(),
            "events": list(self._events),
            "analysis": self._analysis.model_dump() if self._analysis else None,
            "window": {
                "comments": list(self._window_comments),
                "counts": dict(self._window_counts),
            },
            "window_seconds": self._window_seconds,
        }

    def _status_message(self) -> dict[str, Any]:
        return {"type": "status", **self.status_payload()}

    def _broadcast(self, message: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                    queue.put_nowait(message)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        if self._idle_task is not None:
            self._idle_task.cancel()
            self._idle_task = None
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)
        if not self._subscribers and self._running:
            if self._idle_task is None or self._idle_task.done():
                self._idle_task = asyncio.create_task(self._stop_when_idle())

    async def _stop_when_idle(self) -> None:
        await asyncio.sleep(IDLE_STOP_SECONDS)
        if not self._subscribers and self._running:
            await self.stop()

    async def start(self, config: LiveStartRequest | None = None) -> dict[str, Any]:
        async with self._lifecycle_lock:
            if self._running:
                return self.status_payload()

            # Clean up a previously failed/stopped provider before starting a new one.
            if self._tasks or self._provider is not None:
                for task in self._tasks:
                    task.cancel()
                if self._tasks:
                    await asyncio.gather(*self._tasks, return_exceptions=True)
                self._tasks.clear()
                provider, self._provider = self._provider, None
                if provider is not None:
                    with contextlib.suppress(Exception):
                        await provider.stop()

            config = config or LiveStartRequest()
            source = (config.source or "bilibili").strip().lower()
            if source not in {"bilibili", "simulated"}:
                raise LiveSessionError("source 只支持 bilibili 或 simulated")

            if self._idle_task is not None:
                self._idle_task.cancel()
                self._idle_task = None

            self._source = source
            self._error = None
            self._status = "starting"
            self._counts.clear()
            self._window_counts.clear()
            self._window_comments.clear()
            self._events.clear()
            self._analysis = None
            self._last_analysis_at = None
            self._seq = 0
            self._totals = self._empty_totals()
            self._start_elapsed = self._template.live_state.elapsed_seconds
            self._planned_seconds = self._template.live_state.planned_seconds
            self._current_stage = self._template.live_state.current_stage
            self._directive = None
            self._auto_analyze = False
            self._started_monotonic = None
            self._product = self._template.product
            self._backend_metrics = BackendMetrics(online_count=0)
            self._window_seconds = self._default_window_seconds
            self._metrics_sources = {
                "online_count": "pending",
                "cart_click_rate_change": "unavailable",
                "conversion_rate": "unavailable",
            }

            if config.elapsed_seconds is not None:
                self._start_elapsed = config.elapsed_seconds
            if config.planned_seconds is not None:
                self._planned_seconds = config.planned_seconds
            if config.current_stage:
                self._current_stage = config.current_stage
            if config.target_stage and config.target_stage.strip():
                self._directive = StageDirective(
                    target_stage=config.target_stage.strip(),
                    reason="启动时手动选择阶段",
                )
            if config.product is not None:
                self._product = config.product
            self._auto_analyze = bool(config.auto_analyze)
            if config.backend_metrics is not None:
                self._backend_metrics = config.backend_metrics
                self._metrics_sources = {
                    "online_count": "start",
                    "cart_click_rate_change": "start",
                    "conversion_rate": "start",
                }
            if config.window_seconds is not None:
                self._window_seconds = max(3, config.window_seconds)

            self._broadcast(self._status_message())

            try:
                provider = self._provider_factory(source)
                await provider.start()
            except Exception as exc:
                self._status = "error"
                self._error = str(exc)
                self._broadcast(self._status_message())
                raise LiveSessionError(str(exc)) from exc

            self._provider = provider
            self._room_id = getattr(provider, "room_id", None)
            self._running = True
            self._status = "listening"
            self._started_at = int(time.time())
            self._started_monotonic = time.monotonic()
            self._tasks = [
                asyncio.create_task(self._consume_events(), name="live-events"),
                asyncio.create_task(self._analysis_loop(), name="live-analysis"),
            ]
            if source == "bilibili" and self._room_id:
                self._tasks.append(
                    asyncio.create_task(self._room_info_loop(), name="live-room-info")
                )
            self._broadcast(self._status_message())
            return self.status_payload()

    async def stop(self) -> dict[str, Any]:
        async with self._lifecycle_lock:
            if self._idle_task is not None:
                self._idle_task.cancel()
                self._idle_task = None
            if not self._running and self._provider is None:
                self._status = "idle"
                self._directive = None
                return self.status_payload()

            self._running = False
            for task in self._tasks:
                task.cancel()
            if self._tasks:
                await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

            provider, self._provider = self._provider, None
            if provider is not None:
                with contextlib.suppress(Exception):
                    await provider.stop()

            self._status = "stopped"
            self._directive = None
            self._broadcast(self._status_message())
            return self.status_payload()

    async def _consume_events(self) -> None:
        try:
            provider = self._provider
            if provider is None:
                return
            while self._running:
                event = await provider.next_event()
                self._handle_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._running = False
            self._status = "error"
            self._error = f"直播事件接收中断：{type(exc).__name__}"
            self._broadcast(self._status_message())
            self._broadcast(
                {
                    "type": "live-error",
                    "message": self._error,
                    "fatal": True,
                }
            )

    def _handle_event(self, event: LiveEvent) -> None:
        text = (event.text or "").strip()
        value_rmb = self._event_value_rmb(event)
        metrics = dict(event.metrics)
        if event.kind in {"gift", "guard", "super_chat"}:
            metrics["value_rmb"] = round(value_rmb, 2)
        self._seq += 1
        view = {
            "id": self._seq,
            "kind": event.kind,
            "text": text,
            "user": event.user,
            "timestamp": event.timestamp or int(time.time()),
            "received_at": int(time.time()),
            "metrics": metrics,
        }
        self._events.append(view)
        self._counts[event.kind] += 1
        self._window_counts[event.kind] += 1
        self._accumulate_totals(event, value_rmb)
        if event.kind in {"danmaku", "super_chat"} and text:
            self._window_comments.append(text)
            # Keep bounded while auto-analysis is paused.
            if len(self._window_comments) > self._max_events:
                del self._window_comments[: len(self._window_comments) - self._max_events]
        self._broadcast(
            {
                "type": "event",
                "event": view,
                "counts": dict(self._counts),
                "totals": self.totals_payload(),
            }
        )

    async def _analysis_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._window_seconds)
                if not self._running:
                    break
                if not self._auto_analyze:
                    continue
                try:
                    await self._analyze_window()
                except Exception as exc:
                    logger.warning("live window analysis failed: %s", type(exc).__name__)
                    self._broadcast(
                        {
                            "type": "live-error",
                            "message": "本窗口分析失败，已保留上一轮提词，监听继续。",
                            "fatal": False,
                        }
                    )
        except asyncio.CancelledError:
            raise

    def _build_payload(
        self,
        comments: list[str],
        counts: Counter[str],
    ) -> AgentInput:
        payload = self._template.model_copy(deep=True)
        elapsed = self._current_elapsed()
        payload.live_state = payload.live_state.model_copy(
            update={
                "elapsed_seconds": elapsed,
                "planned_seconds": self._planned_seconds,
                "current_stage": self._current_stage,
            }
        )
        payload.product = self._product.model_copy(deep=True)
        payload.backend_metrics = self._backend_metrics.model_copy(deep=True)
        payload.directive = self._directive.model_copy(deep=True) if self._directive else None
        payload.recent_comments = comments
        payload.comment_analysis = CommentAnalysis()
        payload.event_counts = dict(counts)
        return payload

    async def _analyze_window(self) -> AgentOutput | None:
        async with self._analysis_lock:
            comments = list(self._window_comments)
            counts = Counter(self._window_counts)
            self._window_comments.clear()
            self._window_counts.clear()

            if not comments:
                self._broadcast(
                    {
                        "type": "window",
                        "comments": [],
                        "counts": dict(counts),
                        "window_seconds": self._window_seconds,
                        "at": int(time.time()),
                    }
                )
                return None

            started = time.perf_counter()
            output = await analyze_async(self._build_payload(comments, counts))
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._analysis = output
            self._last_analysis_at = int(time.time())
            self._broadcast(
                {
                    "type": "analysis",
                    "output": output.model_dump(),
                    "window_seconds": self._window_seconds,
                    "comments": comments,
                    "counts": dict(counts),
                    "latency_ms": latency_ms,
                    "at": self._last_analysis_at,
                }
            )
            return output

    async def analyze_now(self) -> AgentOutput | None:
        if not self._running:
            raise LiveSessionError("实时监听未启动")
        return await self._analyze_window()

    def update_config(self, update: LiveConfigUpdate) -> dict[str, Any]:
        """Apply product/stage overrides to the running session."""
        if not self._running:
            raise LiveSessionError("实时监听未启动")

        current_elapsed = self._current_elapsed()
        self._start_elapsed = (
            update.elapsed_seconds
            if update.elapsed_seconds is not None
            else current_elapsed
        )
        self._started_monotonic = time.monotonic()

        if update.planned_seconds is not None:
            self._planned_seconds = max(1, update.planned_seconds)
        if update.current_stage:
            self._current_stage = update.current_stage
        if update.product is not None:
            self._product = update.product.model_copy(deep=True)
        if update.target_stage is not None:
            target = update.target_stage.strip()
            self._directive = (
                StageDirective(target_stage=target, reason="运行中手动切换阶段")
                if target
                else None
            )
        if update.auto_analyze is not None:
            self._auto_analyze = update.auto_analyze

        self._broadcast(self._status_message())
        return self.status_payload()

    def update_metrics(self, update: LiveMetricsUpdate) -> dict[str, Any]:
        changes = update.model_dump(exclude_none=True, exclude={"source"})
        if changes:
            self._backend_metrics = self._backend_metrics.model_copy(update=changes)
            for key in changes:
                self._metrics_sources[key] = update.source or "external"
            self._broadcast({"type": "metrics", **self.metrics_payload()})
        return self.metrics_payload()

    async def _room_info_loop(self) -> None:
        timeout = aiohttp.ClientTimeout(total=8)
        last_online: int | None = None
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                while self._running:
                    try:
                        async with session.get(
                            ROOM_INFO_URL,
                            params={"room_id": self._room_id},
                            headers={"User-Agent": "ContentAgent/0.1"},
                        ) as response:
                            if response.status == 200:
                                data = await response.json()
                                info = data.get("data") or {}
                                online = info.get("online")
                                if isinstance(online, int) and online >= 0:
                                    if online != last_online:
                                        last_online = online
                                        self._backend_metrics = (
                                            self._backend_metrics.model_copy(
                                                update={"online_count": online}
                                            )
                                        )
                                        self._metrics_sources["online_count"] = "bilibili"
                                        self._broadcast(
                                            {"type": "metrics", **self.metrics_payload()}
                                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        # Keep the last known metrics; polling is best-effort.
                        pass
                    await asyncio.sleep(ROOM_INFO_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise

    async def stream(self, request: Request):
        queue = self.subscribe()
        try:
            yield _sse("snapshot", self.snapshot())
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield _sse(str(message.get("type", "message")), message)
        finally:
            self.unsubscribe(queue)
