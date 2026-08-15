import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tracker.models import Offer, SourceHealth, SourceResult
from tracker.pipeline import _canonical_laptop_id, run_pipeline


ROOT = Path(__file__).resolve().parents[1]


def result(price=1600, availability="in_stock"):
    offer = Offer(
        id="fixed-offer", source="bestware", seller="Bestware", laptop_id="xmg-core-16-m25-ai9-365-rtx5060",
        url="https://example.test/xmg", price=price, shipping=0, total_price=price,
        availability=availability, confidence="high",
    )
    health = SourceHealth(
        id="bestware-xmg-core-16", source="bestware", url=offer.url, status="ok",
        last_attempt="2026-08-14T12:00:00Z", last_success="2026-08-14T12:00:00Z", offers_found=1,
    )
    return SourceResult(offers=[offer], health=health), {}


class PipelineTests(unittest.TestCase):
    def test_ambiguous_family_sku_does_not_merge_exact_variants(self):
        candidate = {"id": "discovered-core", "brand": "XMG", "model": "CORE 16 (M25)", "sku": "XCO16M25"}
        known = {
            "a": {"id": "core-5060", "brand": "XMG", "model": "CORE 16", "sku": "XCO16M25"},
            "b": {"id": "core-5070", "brand": "XMG", "model": "CORE 16", "sku": "XCO16M25"},
        }

        self.assertEqual(_canonical_laptop_id(candidate, known), "discovered-core")

    def test_two_runs_preserve_price_history(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first"
            second = Path(temp) / "second"
            with patch("tracker.pipeline.run_source", return_value=result(1700)):
                run_pipeline(ROOT, first, None, "watchlist")
            with patch("tracker.pipeline.run_source", return_value=result(1500)):
                dashboard = run_pipeline(ROOT, second, first, "watchlist")
            lines = []
            for path in (second / "history").glob("*.jsonl"):
                lines.extend(path.read_text(encoding="utf-8").splitlines())
            events = [json.loads(line) for line in lines]
            self.assertEqual([event["total_price"] for event in events if event["offer_id"] == "fixed-offer"], [1700, 1500])
            xmg = next(item for item in dashboard["laptops"] if item["id"] == "xmg-core-16-m25-ai9-365-rtx5060")
            self.assertEqual(xmg["history"]["lowest"], 1500)

    def test_failed_source_does_not_remove_previous_offer(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first"
            second = Path(temp) / "second"
            with patch("tracker.pipeline.run_source", return_value=result(1600)):
                run_pipeline(ROOT, first, None, "watchlist")
            failed = SourceResult(health=SourceHealth(
                id="bestware-xmg-core-16", source="bestware", url="https://example.test/xmg",
                status="failed", last_attempt="2026-08-14T13:00:00Z", error="fixture failure",
            )), {}
            with patch("tracker.pipeline.run_source", return_value=failed):
                dashboard = run_pipeline(ROOT, second, first, "watchlist")
            xmg = next(item for item in dashboard["laptops"] if item["id"] == "xmg-core-16-m25-ai9-365-rtx5060")
            self.assertEqual(xmg["best_offer"]["total_price"], 1600)

    def test_offline_generation_has_seed_catalog(self):
        with tempfile.TemporaryDirectory() as temp:
            dashboard = run_pipeline(ROOT, Path(temp) / "data", None, "all", offline=True)
            self.assertGreaterEqual(dashboard["summary"]["tracked_laptops"], 10)
            self.assertEqual(dashboard["summary"]["active_offers"], 0)
            zephyrus = next(item for item in dashboard["laptops"] if item["id"] == "asus-zephyrus-g16-ga605kp-qr022w")
            self.assertEqual(zephyrus["family_id"], "asus-rog-zephyrus-g16-ga605-2025")


if __name__ == "__main__":
    unittest.main()
