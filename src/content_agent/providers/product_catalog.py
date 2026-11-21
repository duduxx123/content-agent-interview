import json
from pathlib import Path

from content_agent.schemas import Product, ProductSellingPoint


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ProductCatalog:
    """Load product facts and match selling points to live audience language."""

    def __init__(self, path: str | Path = PROJECT_ROOT / "config" / "products.json") -> None:
        self._products: dict[str, Product] = {}
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return
        for item in data.get("products", []):
            product = Product.model_validate(item)
            self._products[product.sku_id] = product

    def get(self, sku_id: str) -> Product | None:
        """Return a catalog product by SKU for previews and tests."""
        return self._products.get(sku_id)

    def enrich(self, product: Product) -> Product:
        """Use catalog facts to fill missing fields; live input can update price/stock facts."""
        catalog_product = self._products.get(product.sku_id)
        if catalog_product is None:
            return product
        fields = (
            "selling_points",
            "usage_instructions",
            "applicable_audience",
            "cautions",
            "evidence_notes",
        )
        updates = {
            field: getattr(catalog_product, field)
            for field in fields
            if not getattr(product, field)
        }
        return product.model_copy(update=updates)

    @staticmethod
    def match_selling_points(
        product: Product,
        audience_text: str,
    ) -> list[tuple[ProductSellingPoint, list[str]]]:
        matches: list[tuple[ProductSellingPoint, list[str]]] = []
        normalized_text = audience_text.casefold()
        for point in product.selling_points:
            matched_keywords = [
                keyword
                for keyword in point.match_keywords
                if keyword and keyword.casefold() in normalized_text
            ]
            if matched_keywords:
                matches.append((point, matched_keywords))
        return sorted(
            matches,
            key=lambda item: (len(item[1]), item[0].verified),
            reverse=True,
        )
