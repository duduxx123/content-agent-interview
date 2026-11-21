import json
from pathlib import Path
from typing import Any

from content_agent.schemas import LiveState, StageDirective, StageState


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULES_PATH = PROJECT_ROOT / "config" / "decision_rules.json"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(value, high))


class LiveStructureModule:
    """Derive the current live stage and the preparations for the next stage."""

    def __init__(self, rules_path: str | Path = DEFAULT_RULES_PATH) -> None:
        try:
            data = json.loads(Path(rules_path).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            data = {}
        self.stages: list[dict[str, Any]] = sorted(
            data.get("stages", []),
            key=lambda item: float(item.get("start_ratio", 0)),
        )
        self.after_live_preparation: list[str] = data.get("after_live_preparation", [])

    def _stage_by_name(self, name: str) -> dict[str, Any] | None:
        for stage in self.stages:
            if stage.get("name") == name:
                return stage
        return None

    def _stage_for_ratio(self, ratio: float) -> dict[str, Any] | None:
        if not self.stages:
            return None
        for stage in self.stages:
            start = float(stage.get("start_ratio", 0))
            end = float(stage.get("end_ratio", 1))
            if start <= ratio < end:
                return stage
        return self.stages[-1]

    def _build(
        self,
        stage: dict[str, Any],
        state: LiveState,
        ratio: float,
        *,
        source: str,
        declared: str,
        notes: list[str],
    ) -> StageState:
        name = str(stage.get("name", declared or "未命名阶段"))
        start = float(stage.get("start_ratio", 0))
        end = float(stage.get("end_ratio", 1))
        span = end - start
        planned = state.planned_seconds

        if source == "directive" and not (start <= ratio < end):
            # The instruction jumps into a stage earlier than the clock plan.
            progress = 0.0
            stage_remaining = int(span * planned) if planned > 0 else 0
        else:
            progress = _clamp((ratio - start) / span) if span > 0 else 1.0
            stage_remaining = int(end * planned - state.elapsed_seconds) if planned > 0 else 0

        index = self.stages.index(stage)
        next_stage = self.stages[index + 1] if index + 1 < len(self.stages) else None
        next_name = str(next_stage.get("name")) if next_stage else None
        next_preparation = (
            list(next_stage.get("preparation", []))
            if next_stage
            else list(self.after_live_preparation)
        )

        return StageState(
            current_stage=name,
            declared_stage=declared,
            stage_focus=str(stage.get("focus", "")),
            stage_goal=str(stage.get("goal", "")),
            next_stage=next_name,
            next_stage_preparation=next_preparation,
            stage_progress=round(progress, 3),
            stage_remaining_seconds=max(stage_remaining, 0),
            total_remaining_seconds=max(planned - state.elapsed_seconds, 0),
            source=source,
            notes=notes,
        )

    def evaluate(
        self,
        state: LiveState,
        directive: StageDirective | None = None,
    ) -> StageState:
        declared = state.current_stage.strip() if state.current_stage else ""
        planned = state.planned_seconds
        ratio = _clamp(state.elapsed_seconds / planned) if planned > 0 else 0.0
        clock_stage = self._stage_for_ratio(ratio) if planned > 0 else None
        notes: list[str] = []
        stage = clock_stage
        source = "clock"

        if directive is not None and directive.target_stage.strip():
            target = self._stage_by_name(directive.target_stage.strip())
            if target is not None:
                stage = target
                source = "directive"
                reason = f"（{directive.reason}）" if directive.reason else ""
                notes.append(f"结构化指令生效：进入{target.get('name')}{reason}")
            else:
                notes.append(
                    f"结构化指令指定阶段“{directive.target_stage}”不在阶段计划中，已按时间推算。"
                )

        if stage is None:
            declared_stage = self._stage_by_name(declared)
            if declared_stage is not None:
                stage = declared_stage
                source = "declared"
                notes.append("缺少有效时间计划，按输入声明阶段处理。")
            elif self.stages:
                stage = self.stages[0]
                source = "declared"
                notes.append("无法确定当前阶段，已回退到阶段计划的第一阶段。")
            else:
                return StageState(
                    current_stage=declared or "未配置阶段",
                    declared_stage=declared,
                    source="declared",
                    notes=["未加载阶段计划，仅返回输入声明阶段。"],
                )

        if (
            source == "clock"
            and declared
            and clock_stage is not None
            and declared != clock_stage.get("name")
        ):
            notes.append(
                f"输入声明阶段“{declared}”与时间推算阶段“{clock_stage.get('name')}”不一致，"
                "已按时间推算执行。"
            )

        return self._build(
            stage,
            state,
            ratio,
            source=source,
            declared=declared,
            notes=notes,
        )
