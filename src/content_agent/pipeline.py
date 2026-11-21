import json
import logging
from pathlib import Path

from content_agent.modules.compliance import ComplianceModule
from content_agent.modules.decision_fusion import DecisionFusionModule
from content_agent.modules.interaction import InteractionModule
from content_agent.modules.live_structure import LiveStructureModule
from content_agent.modules.selling_points import SellingPointModule
from content_agent.llm.deepseek import DeepSeekAPIError, DeepSeekClient
from content_agent.providers.product_catalog import ProductCatalog
from content_agent.schemas import AgentInput, AgentOutput, InteractionResult, Suggestion

logger = logging.getLogger(__name__)


def _prepare_payload(payload: AgentInput) -> AgentInput:
    prepared = payload.model_copy(deep=True)
    prepared.product = ProductCatalog().enrich(prepared.product)
    return prepared


def _analyze_prepared(
    payload: AgentInput,
    interactions: InteractionResult | None = None,
) -> AgentOutput:
    stage_state = LiveStructureModule().evaluate(payload.live_state, payload.directive)
    if stage_state.current_stage:
        payload.live_state.current_stage = stage_state.current_stage

    if interactions is None:
        interactions = InteractionModule().analyze(payload)
    payload.comment_analysis = interactions.comment_analysis
    candidates = SellingPointModule().suggest(payload, interactions.summary)
    compliance = ComplianceModule().filter(candidates)
    decision = DecisionFusionModule().rank(payload, compliance, stage_state)

    preparation = "、".join(stage_state.next_stage_preparation) or "无"
    summary = [
        f"直播阶段：{stage_state.current_stage}（{stage_state.stage_goal}）",
        f"下一阶段：{stage_state.next_stage or '无'}；准备：{preparation}",
        *stage_state.notes,
        *interactions.summary,
        *decision.notes,
    ]
    return AgentOutput(
        suggestions=decision.suggestions,
        analysis_summary=summary,
        stage_state=stage_state,
        decision_notes=decision.notes,
        interaction_mode=interactions.mode,
    )


def analyze(payload: AgentInput) -> AgentOutput:
    """Run interaction extraction, catalog matching, filtering, and ranking."""
    return _analyze_prepared(_prepare_payload(payload))


async def analyze_async(payload: AgentInput) -> AgentOutput:
    """Prefer DeepSeek for semantic interaction analysis and concise phrasing."""
    model_payload = _prepare_payload(payload)
    client = DeepSeekClient.from_env()
    interactions: InteractionResult | None = None

    if client is not None and any(
        comment.strip() for comment in model_payload.recent_comments
    ):
        stage_state = LiveStructureModule().evaluate(
            model_payload.live_state,
            model_payload.directive,
        )
        try:
            interactions = await client.analyze_interactions(
                model_payload.recent_comments,
                stage=stage_state.current_stage,
            )
        except Exception as exc:
            # Do not log request headers, keys, comments, or response bodies.
            detail = (
                f"HTTP {exc.status_code}"
                if isinstance(exc, DeepSeekAPIError)
                else type(exc).__name__
            )
            logger.warning(
                "DeepSeek interaction analysis failed (%s); using keyword rules",
                detail,
            )

    output = _analyze_prepared(model_payload, interactions)
    if client is None or not output.suggestions:
        return output

    try:
        output = await client.refine(model_payload, output)
    except Exception as exc:
        # Do not log request headers, keys, or response bodies.
        detail = (
            f"HTTP {exc.status_code}"
            if isinstance(exc, DeepSeekAPIError)
            else type(exc).__name__
        )
        logger.warning("DeepSeek call failed (%s); keeping rule-based suggestions", detail)
        return output

    checked = ComplianceModule().filter(output.suggestions)
    for suggestion in checked:
        if suggestion.compliance_status.startswith(("需复核", "需人工复核")):
            suggestion.priority = "低"
    output.suggestions = sorted(checked, key=lambda item: item.score, reverse=True)
    output.generation_mode = "deepseek"
    return output


def analyze_file(path: str | Path) -> AgentOutput:
    payload = AgentInput.model_validate_json(Path(path).read_text(encoding="utf-8-sig"))
    return analyze(payload)
