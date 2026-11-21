import unittest
from pathlib import Path

from content_agent.main import STATIC_DIR, demo_bootstrap
from content_agent.modules.decision_fusion import DecisionFusionModule
from content_agent.modules.live_structure import LiveStructureModule
from content_agent.pipeline import analyze, analyze_file
from content_agent.schemas import AgentInput, LiveState, StageDirective, Suggestion


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFLICT_SCENE = PROJECT_ROOT / "examples" / "scene_conflict.json"


class DemoBootstrapTests(unittest.TestCase):
    def test_bootstrap_returns_stages_and_valid_scenes(self) -> None:
        data = demo_bootstrap()
        self.assertGreaterEqual(len(data["stages"]), 2)
        self.assertEqual(data["stages"][0]["name"], "预热期")
        self.assertEqual(len(data["scenes"]), 2)
        self.assertGreaterEqual(len(data["products"]), 5)
        self.assertIn("20001", {item["sku_id"] for item in data["products"]})
        for preset in data["scenes"]:
            AgentInput.model_validate(preset["scene"])
        self.assertTrue((STATIC_DIR / "index.html").is_file())


class LiveStructureTests(unittest.TestCase):
    def test_clock_stage_and_next_preparation(self) -> None:
        stage = LiveStructureModule().evaluate(
            LiveState(elapsed_seconds=900, planned_seconds=3600)
        )
        self.assertEqual(stage.current_stage, "产品讲解期")
        self.assertEqual(stage.next_stage, "答疑期")
        self.assertTrue(stage.next_stage_preparation)
        self.assertEqual(stage.source, "clock")

    def test_directive_overrides_clock(self) -> None:
        stage = LiveStructureModule().evaluate(
            LiveState(elapsed_seconds=600, planned_seconds=3600),
            StageDirective(target_stage="促单期", reason="运营要求提前促单"),
        )
        self.assertEqual(stage.current_stage, "促单期")
        self.assertEqual(stage.source, "directive")
        self.assertTrue(any("结构化指令生效" in note for note in stage.notes))


class DecisionFusionTests(unittest.TestCase):
    def test_conflict_keeps_answer_above_promotion(self) -> None:
        output = analyze_file(CONFLICT_SCENE)
        self.assertIsNotNone(output.stage_state)
        self.assertEqual(output.stage_state.current_stage, "促单期")
        self.assertEqual(output.suggestions[0].topic, "肤质")
        self.assertEqual(output.suggestions[0].intent, "答疑")
        self.assertLess(output.suggestions[0].score, 1.0)
        self.assertTrue(any("冲突" in note for note in output.decision_notes))

    def test_promotion_stage_without_answer_pressure(self) -> None:
        payload = AgentInput.model_validate_json(
            CONFLICT_SCENE.read_text(encoding="utf-8")
        )
        payload.recent_comments = ["有没有小样？"]
        payload.event_counts = {}
        output = analyze(payload)
        self.assertEqual(output.suggestions[0].intent, "转化")
        self.assertTrue(
            any("无同问/负面压力" in note for note in output.decision_notes)
        )

    def test_compliance_blocked_item_stays_low(self) -> None:
        payload = AgentInput.model_validate_json(
            CONFLICT_SCENE.read_text(encoding="utf-8")
        )
        blocked = Suggestion(
            priority="中",
            score=0.95,
            suggested_script="全网最低价",
            recommended_action="促单",
            trigger_reason="test",
            compliance_status="需人工复核：命中风险词 全网最低价",
            topic="价格",
            intent="转化",
        )
        outcome = DecisionFusionModule().rank(payload, [blocked])
        self.assertEqual(outcome.suggestions[0].priority, "低")
        self.assertEqual(outcome.suggestions[0].score, 0.1)


if __name__ == "__main__":
    unittest.main()
