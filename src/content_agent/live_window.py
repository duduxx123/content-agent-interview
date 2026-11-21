import asyncio
import json
from collections import Counter
from pathlib import Path
from time import monotonic

from content_agent.modules.live_structure import LiveStructureModule
from content_agent.pipeline import analyze_async
from content_agent.providers.base import LiveDataProvider
from content_agent.schemas import AgentInput, BackendMetrics, LiveEvent


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class LiveWindowRunner:
    """Batch incoming platform events and run the agent once per time window."""

    def __init__(
        self,
        provider: LiveDataProvider,
        *,
        template_path: str | Path = PROJECT_ROOT / "examples" / "scene.json",
        window_seconds: int = 30,
    ) -> None:
        if window_seconds < 1:
            raise ValueError("window_seconds must be at least 1")
        self.provider = provider
        self.window_seconds = window_seconds
        self.template = AgentInput.model_validate_json(
            Path(template_path).read_text(encoding="utf-8-sig")
        )

    async def run(self) -> None:
        await self.provider.start()
        started_at = monotonic()
        print(
            f"B 站直播 Agent 已启动；每 {self.window_seconds} 秒汇总一次。"
            "按 Ctrl+C 停止。",
            flush=True,
        )
        try:
            while True:
                events = await self._collect_window()
                elapsed = int(monotonic() - started_at)
                await self._show_window(events, elapsed)
        finally:
            await self.provider.stop()

    async def _collect_window(self) -> list[LiveEvent]:
        events: list[LiveEvent] = []
        deadline = monotonic() + self.window_seconds
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return events
            try:
                event = await asyncio.wait_for(self.provider.next_event(), timeout=remaining)
            except asyncio.TimeoutError:
                return events
            events.append(event)

    async def _show_window(self, events: list[LiveEvent], elapsed_seconds: int) -> None:
        counts = Counter(event.kind for event in events)
        comments = [
            event.text.strip()
            for event in events
            if event.kind in {"danmaku", "super_chat"} and event.text.strip()
        ]

        print(f"\n--- 最近 {self.window_seconds} 秒 | 收到 {len(events)} 个事件 ---", flush=True)
        if counts:
            print("事件统计：" + "、".join(f"{kind} {count} 条" for kind, count in counts.items()), flush=True)

        payload = self.template.model_copy(deep=True)
        # elapsed_seconds is the total runtime, so add it to the template baseline once.
        payload.live_state.elapsed_seconds = (
            self.template.live_state.elapsed_seconds + elapsed_seconds
        )
        # Bilibili's public feed does not expose cart clicks or conversion.
        payload.backend_metrics = BackendMetrics(online_count=0)
        stage = LiveStructureModule().evaluate(payload.live_state, payload.directive)
        payload.live_state.current_stage = stage.current_stage
        preparation = "、".join(stage.next_stage_preparation) or "无"
        print(
            f"直播阶段：{stage.current_stage}（{stage.stage_goal}，"
            f"本阶段剩余 {stage.stage_remaining_seconds} 秒）",
            flush=True,
        )
        print(
            f"下一阶段：{stage.next_stage or '无'}；准备：{preparation}",
            flush=True,
        )
        for note in stage.notes:
            print(f"  阶段提示：{note}", flush=True)

        if not comments:
            print("本窗口没有可分析的弹幕或醒目留言。", flush=True)
            return

        payload.recent_comments = comments
        payload.event_counts = dict(counts)
        output = await analyze_async(payload)

        print("互动摘要：", flush=True)
        for item in output.analysis_summary:
            if item.startswith(("直播阶段：", "下一阶段：")):
                continue  # Already printed above.
            print(f"  - {item}", flush=True)
        print("提词建议：", flush=True)
        for suggestion in output.suggestions:
            print(f"  [{suggestion.priority}] {suggestion.suggested_script}", flush=True)
            print(f"    动作：{suggestion.recommended_action}", flush=True)
            print(f"    原因：{suggestion.trigger_reason}", flush=True)
            print(f"    合规：{suggestion.compliance_status}", flush=True)
            for alternative in suggestion.compliance_replacements:
                print(f"    替代表达：{alternative}", flush=True)
        print(f"提词生成方式：{output.generation_mode}", flush=True)

        print(
            "后台指标：B 站公开接口不提供购物车点击率和成交转化率，"
            "监听器不使用这两项；在线人数可在 Web 实时页面查看。",
            flush=True,
        )
