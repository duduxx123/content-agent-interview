import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from content_agent.modules.interaction import classify_topics
from content_agent.schemas import AgentInput, StageState, Suggestion


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULES_PATH = PROJECT_ROOT / "config" / "decision_rules.json"
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")

DEFAULT_SCORING = {
    "base_weight": 0.6,
    "signal_weight": 0.4,
    "signal_scale": 0.6,
    "topic_match_weight": 0.02,
    "topic_match_cap": 0.08,
    "negative_feedback": 0.08,
    "purchase_intent": 0.05,
    "repeated_question_weight": 0.08,
    "repeated_question_cap": 0.2,
    "spam_weight": 0.04,
    "spam_cap": 0.08,
    "super_chat": 0.05,
    "gift": 0.01,
    "event_cap": 0.1,
    "cart_click_rise": 0.05,
    "cart_click_drop": -0.04,
    "low_conversion": 0.05,
    "online_audience": 0.03,
    "stage_focus_match": 0.1,
    "stage_focus_mismatch": -0.04,
}
DEFAULT_THRESHOLDS = {
    "high_priority": 0.75,
    "medium_priority": 0.6,
    "repeated_alert": 2,
    "spam_alert": 3,
    "online_high": 1000,
    "conversion_low": 3.0,
    "cart_change_alert": 2.0,
    "score_cap": 1.0,
}
DEFAULT_CONFLICTS = {
    "answer_vs_promote": {
        "enabled": True,
        "promote_focus": "转化",
        "answer_intents": ["答疑"],
        "promote_intents": ["转化"],
        "repeated_threshold": 2,
        "negative_requires_answer": True,
        "answer_interrupt_bonus": 0.15,
        "promote_defer_penalty": -0.08,
    },
    "compliance_override": {
        "trigger_prefixes": ["需复核", "需人工复核"],
        "priority": "低",
        "score_cap": 0.1,
    },
}


@dataclass
class DecisionOutcome:
    suggestions: list[Suggestion]
    notes: list[str] = field(default_factory=list)


def _first_number(text: str) -> float | None:
    match = _NUMBER_RE.search(text or "")
    return float(match.group()) if match else None


def _parse_percent(text: str) -> float | None:
    value = _first_number(text)
    return abs(value) if value is not None else None


def _parse_trend(text: str) -> float | None:
    """Parse values such as '上升5%', '+5%' or '下降3%' into signed points."""
    value = _first_number(text)
    if value is None:
        return None
    if any(word in text for word in ("下降", "降低", "减少", "下滑")):
        return -abs(value)
    if any(word in text for word in ("上升", "提高", "增长", "上涨")):
        return abs(value)
    return value


class DecisionFusionModule:
    """Score candidates from interaction, product, backend and stage signals."""

    def __init__(self, rules_path: str | Path = DEFAULT_RULES_PATH) -> None:
        try:
            data: dict[str, Any] = json.loads(
                Path(rules_path).read_text(encoding="utf-8-sig")
            )
        except (OSError, json.JSONDecodeError):
            data = {}
        self.scoring = {**DEFAULT_SCORING, **data.get("scoring", {})}
        self.thresholds = {**DEFAULT_THRESHOLDS, **data.get("thresholds", {})}
        raw_conflicts = data.get("conflicts", {})
        self.conflicts = {
            "answer_vs_promote": {
                **DEFAULT_CONFLICTS["answer_vs_promote"],
                **raw_conflicts.get("answer_vs_promote", {}),
            },
            "compliance_override": {
                **DEFAULT_CONFLICTS["compliance_override"],
                **raw_conflicts.get("compliance_override", {}),
            },
        }

    def _repeat_topic_counts(
        self, payload: AgentInput
    ) -> tuple[Counter[str], Counter[str], int, int]:
        analysis = payload.comment_analysis
        repeat_topics: Counter[str] = Counter()
        for text, count in analysis.repeated_questions.items():
            for topic in classify_topics(text):
                repeat_topics[topic] += count
        spam_topics: Counter[str] = Counter()
        for text, count in analysis.repeated_comments.items():
            for topic in classify_topics(text):
                spam_topics[topic] += count
        max_question = max(analysis.repeated_questions.values(), default=0)
        max_spam = max(analysis.repeated_comments.values(), default=0)
        return repeat_topics, spam_topics, max_question, max_spam

    def rank(
        self,
        payload: AgentInput,
        candidates: list[Suggestion],
        stage_state: StageState | None = None,
    ) -> DecisionOutcome:
        scoring = self.scoring
        thresholds = self.thresholds
        analysis = payload.comment_analysis
        notes: list[str] = []

        repeat_topics, spam_topics, max_question, max_spam = self._repeat_topic_counts(
            payload
        )
        stage_focus = stage_state.stage_focus if stage_state else ""

        conflict = self.conflicts["answer_vs_promote"]
        in_promote_stage = bool(
            conflict.get("enabled", True)
            and stage_focus == conflict.get("promote_focus", "转化")
        )
        answer_pressure = (
            max_question >= int(conflict.get("repeated_threshold", 2))
            or (
                bool(conflict.get("negative_requires_answer", True))
                and bool(analysis.negative_feedback)
            )
        )
        apply_conflict = in_promote_stage and answer_pressure

        compliance_cfg = self.conflicts["compliance_override"]
        blocked_prefixes = tuple(
            compliance_cfg.get("trigger_prefixes", ["需复核", "需人工复核"])
        )
        blocked_priority = str(compliance_cfg.get("priority", "低"))
        blocked_score_cap = float(compliance_cfg.get("score_cap", 0.1))
        blocked_count = 0

        base_weight = float(scoring["base_weight"])
        signal_weight = float(scoring["signal_weight"])
        signal_scale = max(float(scoring["signal_scale"]), 1e-6)

        events = payload.event_counts
        event_bonus = min(
            float(events.get("super_chat", 0)) * float(scoring["super_chat"])
            + float(events.get("gift", 0)) * float(scoring["gift"]),
            float(scoring["event_cap"]),
        )
        backend = payload.backend_metrics
        cart_trend = _parse_trend(backend.cart_click_rate_change)
        conversion = _parse_percent(backend.conversion_rate)
        cart_alert = float(thresholds["cart_change_alert"])
        conversion_low = float(thresholds["conversion_low"])

        for item in candidates:
            if item.compliance_status.startswith(blocked_prefixes):
                item.priority = blocked_priority
                item.score = min(item.score, blocked_score_cap)
                blocked_count += 1
                continue

            bonus = 0.0

            topic_count = analysis.hot_words.get(item.topic, 0)
            bonus += min(
                topic_count * float(scoring["topic_match_weight"]),
                float(scoring["topic_match_cap"]),
            )

            if analysis.negative_feedback and item.intent in {"答疑", "转化"}:
                bonus += float(scoring["negative_feedback"])
            if analysis.purchase_intent and item.intent == "转化":
                bonus += float(scoring["purchase_intent"])

            repeat_count = repeat_topics.get(item.topic, 0)
            if repeat_count >= int(thresholds["repeated_alert"]):
                bonus += min(
                    repeat_count * float(scoring["repeated_question_weight"]),
                    float(scoring["repeated_question_cap"]),
                )

            spam_count = spam_topics.get(item.topic, 0)
            if spam_count >= int(thresholds["spam_alert"]):
                bonus += min(
                    spam_count * float(scoring["spam_weight"]),
                    float(scoring["spam_cap"]),
                )

            bonus += event_bonus

            if item.intent == "转化":
                if cart_trend is not None:
                    if cart_trend >= cart_alert:
                        bonus += float(scoring["cart_click_rise"])
                    elif cart_trend <= -cart_alert:
                        bonus += float(scoring["cart_click_drop"])
                if conversion is not None and conversion < conversion_low:
                    bonus += float(scoring["low_conversion"])
                if (
                    backend.online_count >= int(thresholds["online_high"])
                    and stage_focus == "转化"
                ):
                    bonus += float(scoring["online_audience"])

            if stage_focus in {"答疑", "转化", "讲解"}:
                if item.intent == stage_focus:
                    bonus += float(scoring["stage_focus_match"])
                else:
                    bonus += float(scoring["stage_focus_mismatch"])

            if apply_conflict:
                if item.intent in conflict.get("answer_intents", ["答疑"]):
                    bonus += float(conflict.get("answer_interrupt_bonus", 0.12))
                if item.intent in conflict.get("promote_intents", ["转化"]):
                    bonus += float(conflict.get("promote_defer_penalty", -0.06))

            # Blend the product-based base score with normalized live signals so
            # conflicting signals stay visible instead of every item saturating at 1.0.
            base = min(max(item.score, 0.0), 1.0)
            signal_strength = min(max(bonus / signal_scale, 0.0), 1.0)
            score = base * base_weight + signal_strength * signal_weight
            cap = float(thresholds["score_cap"])
            item.score = round(min(max(score, 0.0), cap), 3)
            if item.score >= float(thresholds["high_priority"]):
                item.priority = "高"
            elif item.score >= float(thresholds["medium_priority"]):
                item.priority = "中"
            else:
                item.priority = "低"

        if blocked_count:
            notes.append(
                f"{blocked_count} 条建议命中合规风险，已降为低优先级并暂缓播报。"
            )

        if max_spam >= int(thresholds["spam_alert"]):
            if spam_topics:
                notes.append(
                    f"检测到刷屏文本，最高重复 {max_spam} 次；相关卖点建议已加权。"
                )
            else:
                notes.append(
                    f"检测到刷屏文本，最高重复 {max_spam} 次；未匹配到商品话题，未调整提词。"
                )

        if apply_conflict:
            reasons: list[str] = []
            if max_question:
                reasons.append(f"同问最高 {max_question} 次")
            if analysis.negative_feedback:
                reasons.append("存在负面反馈")
            notes.append(
                f"促单期与答疑需求冲突：{'、'.join(reasons)}，"
                "已为答疑建议预留更高优先级，并暂缓转化类建议。"
            )
        elif in_promote_stage:
            notes.append("处于促单期且无同问/负面压力，转化类建议已加权。")

        if stage_state is not None and stage_state.source == "directive":
            notes.append(f"当前阶段由结构化指令指定：{stage_state.current_stage}。")
            if apply_conflict:
                notes.append("结构化指令决定进入促单，但同问/负面达到阈值，已保留答疑插播。")

        ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
        return DecisionOutcome(suggestions=ranked, notes=notes)
