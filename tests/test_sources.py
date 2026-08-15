import json
import unittest
from unittest.mock import patch

from tracker.sources.structured import _availability, _bestware_catalog_products, _configuration_match, _infer_laptop, _products, run_source
from tracker.utils import number, stable_id


HTML = """
<html><head><script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "Example 16 RTX 5060 32 GB 1 TB",
  "sku": "ABC-123",
  "brand": {"@type": "Brand", "name": "Example"},
  "offers": {"@type": "Offer", "price": "1.499,00 €", "priceCurrency": "EUR", "availability": "https://schema.org/InStock"}
}
</script></head></html>
"""


class SourceTests(unittest.TestCase):
    def test_extracts_json_ld_product(self):
        products = _products(HTML)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["sku"], "ABC-123")

    def test_parses_european_price(self):
        self.assertEqual(number("1.499,00 €"), 1499.0)

    def test_normalizes_availability(self):
        self.assertEqual(_availability("https://schema.org/InStock"), "in_stock")
        self.assertEqual(_availability("https://schema.org/OutOfStock"), "out_of_stock")

    def test_stable_offer_identity(self):
        self.assertEqual(stable_id("seller", "url", "sku"), stable_id("seller", "url", "sku"))

    def test_bestware_catalog_fallback(self):
        html = '''<product-card><div class="product-card-vendor"><a>XMG</a></div>
        <a href="/en/products/xmg-core-16-m25" class="product-card-title">CORE 16 (M25)</a>
        <div class="feature"><span>NVIDIA GeForce RTX 5060 | 8 GB</span></div>
        <span class="price"><ins><span class="amount ">1.579,00 €</span></ins></span></product-card>'''
        products = _bestware_catalog_products(html, "https://bestware.com/en/gaming-laptops")
        self.assertEqual(products[0]["sku"], "M25")
        self.assertEqual(number(products[0]["offers"]["price"]), 1579.0)

    def test_models_sharing_generation_do_not_collide(self):
        source = {"seller": "Bestware"}
        core = _infer_laptop({"name": "CORE 16 (M25) RTX 5060", "model": "CORE 16 (M25)", "sku": "M25", "brand": {"name": "XMG"}}, source)
        fusion = _infer_laptop({"name": "FUSION 16 (M25) RTX 5060", "model": "FUSION 16 (M25)", "sku": "M25", "brand": {"name": "XMG"}}, source)
        self.assertNotEqual(core["id"], fusion["id"])

    def test_exact_source_fingerprint_matches(self):
        source = {"expected_sku": "ABC-123", "expected_fingerprint": {"gpu": "RTX 5060", "ram_gb": 32, "ssd_gb": 1000}}
        self.assertEqual(_configuration_match(HTML, source)[0], "matched")

    def test_changed_gpu_cannot_attach_to_old_configuration(self):
        source = {"expected_fingerprint": {"gpu": "RTX 5070"}}
        status, details = _configuration_match(HTML, source)
        self.assertEqual(status, "mismatched")
        self.assertIn("RTX 5070", details)

    @patch("tracker.sources.structured.urlopen")
    def test_active_cooldown_skips_network_request(self, mocked_urlopen):
        source = {
            "id": "example", "source": "example", "seller": "Example",
            "url": "https://example.invalid/laptop", "type": "product",
        }
        cache = {
            "cooldown_until": "2999-01-01T00:00:00Z",
            "last_error": "HTTP 403; retries paused",
        }

        result, updated_cache = run_source(source, cache)

        self.assertEqual(result.health.status, "cooldown")
        self.assertEqual(updated_cache, cache)
        mocked_urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
