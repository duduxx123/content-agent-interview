import json
import unittest
from pathlib import Path

from content_agent.pipeline import analyze
from content_agent.providers.product_catalog import ProductCatalog
from content_agent.schemas import AgentInput, LiveState, Product


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_PATH = PROJECT_ROOT / "config" / "products.json"

# One audience question per SKU, chosen to hit a configured selling point.
PRODUCT_CASES = {
    "12345": ("油皮能用吗", "肤质"),
    "20001": ("敏感肌能用吗", "肤质"),
    "20002": ("保湿效果怎么样", "功效"),
    "20003": ("怎么补涂", "用法"),
    "20004": ("成分里有积雪草吗", "成分"),
}


class ProductCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8-sig"))
        self.catalog = ProductCatalog()

    def test_catalog_has_multiple_valid_products(self) -> None:
        products = self.data["products"]
        sku_ids = [item["sku_id"] for item in products]

        self.assertGreaterEqual(len(products), 5)
        self.assertEqual(len(sku_ids), len(set(sku_ids)))
        for item in products:
            product = Product.model_validate(item)
            self.assertTrue(product.name)
            self.assertTrue(product.specification)
            self.assertTrue(product.selling_points)
            for point in product.selling_points:
                self.assertTrue(point.topic)
                self.assertTrue(point.label)
                self.assertTrue(point.description)
                self.assertTrue(point.match_keywords)
                self.assertTrue(point.evidence)
                self.assertIsInstance(point.verified, bool)

    def test_catalog_enriches_product_facts(self) -> None:
        for sku_id in PRODUCT_CASES:
            with self.subTest(sku_id=sku_id):
                enriched = self.catalog.enrich(Product(sku_id=sku_id, name="测试商品"))
                self.assertTrue(enriched.selling_points)
                if sku_id != "12345":
                    self.assertTrue(enriched.usage_instructions)
                    self.assertTrue(enriched.applicable_audience)
                    self.assertTrue(enriched.cautions)
                    self.assertTrue(enriched.evidence_notes)


class ProductAgentTests(unittest.TestCase):
    def test_each_product_reaches_its_selling_point(self) -> None:
        for sku_id, (comment, expected_topic) in PRODUCT_CASES.items():
            with self.subTest(sku_id=sku_id):
                product = ProductCatalog().get(sku_id)
                self.assertIsNotNone(product)
                payload = AgentInput(
                    live_state=LiveState(elapsed_seconds=900, planned_seconds=3600),
                    recent_comments=[comment],
                    product=Product(sku_id=sku_id, name=product.name),
                )
                output = analyze(payload)

                self.assertIsNotNone(output.stage_state)
                self.assertEqual(output.stage_state.current_stage, "产品讲解期")
                self.assertTrue(output.suggestions)
                self.assertTrue(
                    any(item.topic == expected_topic for item in output.suggestions),
                    f"{sku_id} expected topic {expected_topic}, got "
                    f"{[item.topic for item in output.suggestions]}",
                )
                self.assertEqual(output.generation_mode, "rules")
                for suggestion in output.suggestions:
                    self.assertGreaterEqual(suggestion.score, 0.0)
                    self.assertLessEqual(suggestion.score, 1.0)
                    self.assertFalse(
                        suggestion.compliance_status.startswith("需人工复核"),
                        f"{sku_id} unexpectedly blocked: {suggestion.compliance_status}",
                    )


if __name__ == "__main__":
    unittest.main()
