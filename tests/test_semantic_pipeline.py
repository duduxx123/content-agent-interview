import json
import unittest
from pathlib import Path
from unittest.mock import patch

from content_agent.llm.deepseek import DeepSeekClient
from content_agent.pipeline import analyze, analyze_async
from content_agent.schemas import (
    AgentInput,
    CommentAnalysis,
    InteractionResult,
    LiveState,
    Product,
)


class FakeSemanticClient:
    def __init__(self, fail_semantic: bool = False) -> None:
        self.fail_semantic = fail_semantic
        self.stage = None

    async def analyze_interactions(
        self,
        comments: list[str],
        *,
        stage: str | None = None,
    ) -> InteractionResult:
        self.stage = stage
        if self.fail_semantic:
            raise RuntimeError("semantic failure")
        return InteractionResult(
            comment_analysis=CommentAnalysis(
                hot_words={"价格": 2, "肤质": 1},
                questions=["这款多少钱"],
                negative_feedback=["价格有点高"],
                purchase_intent=["想买"],
                repeated_questions={"这款多少钱": 2},
            ),
            summary=[
                "AI 语义分析：测试窗口 3 条文本",
                "高频关注：价格（2条）",
            ],
            mode="deepseek",
        )

    async def refine(self, payload: AgentInput, output):
        output.generation_mode = "deepseek"
        return output


def make_payload() -> AgentInput:
    return AgentInput(
        live_state=LiveState(elapsed_seconds=900, planned_seconds=3600),
        recent_comments=["这款多少钱", "这款多少钱", "价格有点高"],
        product=Product(sku_id="12345", name="控油修护精华液"),
    )


class SemanticResponseParsingTests(unittest.TestCase):
    def test_model_topic_labels_are_normalized(self) -> None:
        normalized = DeepSeekClient._normalize_topics(
            {"价格与优惠": 2, "适用肤质": 1, "使用方法": 1}
        )
        self.assertEqual(normalized["价格"], 2)
        self.assertEqual(normalized["肤质"], 1)
        self.assertEqual(normalized["用法"], 1)

    def test_malformed_repeated_question_object_is_repaired(self) -> None:
        parsed = DeepSeekClient._parse_semantic(
            '{"hot_words":{"价格":2},'
            '"repeated_questions":{"多少钱：2次","干皮能用吗：2次"}}'
        )
        cleaned = DeepSeekClient._clean_pairs(parsed.repeated_questions)
        self.assertEqual(cleaned, {"多少钱": 2, "干皮能用吗": 2})


class StagePromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_refine_prompt_contains_current_stage(self) -> None:
        payload = AgentInput.model_validate_json(
            Path("examples/scene_conflict.json").read_text(encoding="utf-8-sig")
        )
        output = analyze(payload)
        client = DeepSeekClient(api_key="test")
        captured: dict[str, list[dict[str, str]]] = {}

        async def fake_post(messages, *, max_tokens=1200, temperature=0.2):
            captured["messages"] = messages
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "index": index,
                            "suggested_script": item.suggested_script,
                            "recommended_action": item.recommended_action,
                        }
                        for index, item in enumerate(output.suggestions)
                    ],
                    "decision_summary": "当前处于促单期，优先处理价格与答疑冲突。",
                },
                ensure_ascii=False,
            )

        with patch.object(client, "_post_json", new=fake_post):
            await client.refine(payload, output)

        system_prompt = captured["messages"][0]["content"]
        user_prompt = captured["messages"][1]["content"]
        self.assertIn("预热期", system_prompt)
        self.assertIn("促单期", system_prompt)
        self.assertIn("decision_summary", system_prompt)
        self.assertIn('"current_stage": "促单期"', user_prompt)
        self.assertIn('"stage_context"', user_prompt)
        self.assertEqual(
            output.ai_decision_summary,
            "当前处于促单期，优先处理价格与答疑冲突。",
        )


class SemanticPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_semantic_interaction_result_is_used(self) -> None:
        client = FakeSemanticClient()
        with patch(
            "content_agent.pipeline.DeepSeekClient.from_env",
            return_value=client,
        ):
            output = await analyze_async(make_payload())

        self.assertEqual(client.stage, "产品讲解期")
        self.assertEqual(output.interaction_mode, "deepseek")
        self.assertEqual(output.generation_mode, "deepseek")
        self.assertTrue(
            any("AI 语义分析" in line for line in output.analysis_summary)
        )
        self.assertTrue(
            any("价格" in line for line in output.analysis_summary)
        )

    async def test_semantic_failure_falls_back_to_keyword_rules(self) -> None:
        with patch(
            "content_agent.pipeline.DeepSeekClient.from_env",
            return_value=FakeSemanticClient(fail_semantic=True),
        ):
            output = await analyze_async(make_payload())

        self.assertEqual(output.interaction_mode, "rules")
        self.assertEqual(output.generation_mode, "deepseek")
        self.assertTrue(
            any("本窗口收到" in line for line in output.analysis_summary)
        )


if __name__ == "__main__":
    unittest.main()
