import json
import unittest
from pathlib import Path

from content_agent.modules.compliance import SAFE_HOLD_TEXT, ComplianceModule
from content_agent.schemas import Suggestion


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = PROJECT_ROOT / "config" / "compliance_rules.json"


def make_suggestion(script: str, action: str = "按商品资料介绍") -> Suggestion:
    return Suggestion(
        priority="中",
        score=0.8,
        suggested_script=script,
        recommended_action=action,
        trigger_reason="test",
        compliance_status="待检查",
    )


class ComplianceRulesTests(unittest.TestCase):
    def test_rules_have_at_least_100_unique_terms_and_replacements(self) -> None:
        data = json.loads(RULES_PATH.read_text(encoding="utf-8-sig"))
        groups = data["groups"]
        terms = [term for group in groups for term in group["terms"]]

        self.assertGreaterEqual(len(terms), 100)
        self.assertEqual(len(terms), len(set(terms)))
        for group in groups:
            self.assertTrue(group["category"])
            self.assertTrue(group["replacement"])
            self.assertIn(group["risk_level"], {"high_review", "review"})
            self.assertTrue(all(term.strip() for term in group["terms"]))


class ComplianceSemanticFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = ComplianceModule()

    def _hit_terms(self, text: str) -> list[str]:
        return [item["term"] for item in self.module.screen(text)["hits"]]

    def test_absolute_price_claim_is_a_hit(self) -> None:
        self.assertEqual(self._hit_terms("全网最低价，赶紧下单"), ["全网最低价"])

    def test_spacing_width_and_separator_variants_are_normalized(self) -> None:
        self.assertIn("全网最低", self._hit_terms("全 网 最 低"))
        self.assertIn("全网最低", self._hit_terms("全/网/最-低"))
        self.assertIn("100%有效", self._hit_terms("１００％有效"))

    def test_equivalent_percentage_and_zero_phrases_are_matched(self) -> None:
        self.assertIn("100%有效", self._hit_terms("百分百有效"))
        self.assertIn("零风险", self._hit_terms("0风险"))
        self.assertIn("无副作用", self._hit_terms("这款产品没有副作用"))

    def test_negated_claim_is_exempt(self) -> None:
        screen = self.module.screen("这款产品不是全网最低价")
        self.assertEqual(screen["hits"], [])
        self.assertTrue(screen["exempt"])
        self.assertIn("否定", screen["exempt"][0]["reason"])

    def test_disclaimer_claim_is_exempt(self) -> None:
        self.assertEqual(self._hit_terms("无法保证100%有效"), [])
        self.assertEqual(self._hit_terms("不是100%有效"), [])

    def test_question_or_attribution_is_exempt(self) -> None:
        self.assertEqual(self._hit_terms("有人问是不是全网最低"), [])
        self.assertEqual(self._hit_terms("据说全网最低"), [])
        self.assertEqual(self._hit_terms("全网最低吗？"), [])

    def test_procedural_phrases_are_not_flagged(self) -> None:
        for text in ("第一步先清洁", "第一时间联系客服", "唯一编号A1", "最高温度40度"):
            with self.subTest(text=text):
                self.assertEqual(self._hit_terms(text), [])

    def test_best_advice_is_exempt_but_superlative_is_not(self) -> None:
        self.assertEqual(self._hit_terms("最好先看商品详情"), [])
        self.assertEqual(self._hit_terms("最好的产品"), ["最好"])

    def test_medical_claim_with_negation_is_exempt(self) -> None:
        screen = self.module.screen("这款产品不能治疗")
        self.assertEqual(screen["hits"], [])
        self.assertTrue(screen["exempt"])
        self.assertIn("否定", screen["exempt"][0]["reason"])

    def test_negation_scope_with_adverbs_is_exempt(self) -> None:
        self.assertEqual(self._hit_terms("这款产品并非毫无副作用"), [])
        self.assertEqual(self._hit_terms("这款产品毫无副作用"), ["无副作用"])


class ComplianceFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = ComplianceModule()

    def test_blocked_item_is_held_and_downgraded(self) -> None:
        suggestion = make_suggestion("全网最低价", "马上促单")
        result = self.module.filter([suggestion])[0]

        self.assertEqual(result.suggested_script, SAFE_HOLD_TEXT)
        self.assertEqual(result.priority, "低")
        self.assertEqual(result.score, 0.1)
        self.assertTrue(result.compliance_status.startswith("需人工复核"))
        self.assertTrue(result.compliance_replacements)
        self.assertIn("全网最低价", result.compliance_status)

    def test_exempt_text_keeps_script_and_reports_context(self) -> None:
        suggestion = make_suggestion("这款产品不是全网最低价，请以商品详情为准。")
        result = self.module.filter([suggestion])[0]

        self.assertEqual(
            result.suggested_script,
            "这款产品不是全网最低价，请以商品详情为准。",
        )
        self.assertIn("已排除", result.compliance_status)
        self.assertEqual(result.priority, "中")
        self.assertEqual(result.score, 0.8)

    def test_clean_text_passes_pre_screening(self) -> None:
        suggestion = make_suggestion("这款产品规格为30ml，请以商品详情为准。")
        result = self.module.filter([suggestion])[0]

        self.assertEqual(result.compliance_status, "通过词库预筛查（仍需按语境复核）")
        self.assertEqual(result.compliance_replacements, [])


if __name__ == "__main__":
    unittest.main()
