import unittest

from content_agent.main import STATIC_DIR, compliance_page, compliance_rules


class CompliancePageTests(unittest.TestCase):
    def test_static_assets_exist(self) -> None:
        for filename in ("compliance.html", "compliance.css", "compliance.js"):
            with self.subTest(filename=filename):
                self.assertTrue((STATIC_DIR / filename).is_file())

    def test_page_returns_html_file(self) -> None:
        response = compliance_page()
        self.assertTrue(str(response.path).endswith("compliance.html"))

    def test_rules_payload_is_browsable(self) -> None:
        data = compliance_rules()
        groups = data["groups"]
        terms = [term for group in groups for term in group["terms"]]

        self.assertGreaterEqual(len(groups), 5)
        self.assertGreaterEqual(len(set(terms)), 100)
        self.assertTrue(data.get("notice"))
        for group in groups:
            self.assertTrue(group["category"])
            self.assertTrue(group["replacement"])
            self.assertIn(group["risk_level"], {"high_review", "review"})


if __name__ == "__main__":
    unittest.main()
