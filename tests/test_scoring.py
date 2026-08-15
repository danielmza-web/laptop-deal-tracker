import json
import unittest
from copy import deepcopy
from pathlib import Path

from tracker.scoring import decision, effective_price_breakdown, laptop_score, value_score


ROOT = Path(__file__).resolve().parents[1]
PREFERENCES = json.loads((ROOT / "config" / "preferences.yaml").read_text(encoding="utf-8"))
LAPTOPS = {item["id"]: item for item in json.loads((ROOT / "config" / "laptops.json").read_text(encoding="utf-8"))}


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.laptop = deepcopy(LAPTOPS["xmg-core-16-m25-ai7-350-rtx5060"])
        self.offer = {
            "price": 1500,
            "shipping": 20,
            "condition": "new",
            "confidence": "high",
            "configuration_match": "matched",
            "os_status": "no_os",
            "ram_gb": 16,
            "ssd_gb": 512,
        }

    def test_all_catalog_scores_reproduce_with_half_up_rounding(self):
        for laptop in LAPTOPS.values():
            self.assertEqual(laptop.get("laptop_score"), laptop_score(laptop, PREFERENCES), laptop["id"])

    def test_effective_price_includes_windows_ram_ssd_and_shipping(self):
        breakdown = effective_price_breakdown(self.laptop, self.offer, PREFERENCES)
        self.assertEqual(breakdown["listing_price"], 1500)
        self.assertEqual(breakdown["shipping"], 20)
        self.assertEqual(breakdown["windows"], 50)
        self.assertEqual(breakdown["ram"], 90)
        self.assertEqual(breakdown["ssd"], 70)
        self.assertEqual(breakdown["effective_price"], 1730)

    def test_allowances_change_value_but_not_laptop_score(self):
        low = deepcopy(PREFERENCES)
        high = deepcopy(PREFERENCES)
        high["cost_allowances"] = {**high["cost_allowances"], "windows": 150, "ram_32gb": 180, "ssd_1tb": 140}
        hardware_before = laptop_score(self.laptop, low)
        low_value = value_score(self.laptop, self.offer, hardware_before, low)
        high_value = value_score(self.laptop, self.offer, hardware_before, high)
        self.assertEqual(hardware_before, laptop_score(self.laptop, high))
        self.assertGreater(low_value, high_value)

    def test_lower_effective_price_improves_value_score(self):
        score = laptop_score(self.laptop, PREFERENCES)
        lower = {**self.offer, "price": 1400}
        higher = {**self.offer, "price": 2100}
        self.assertGreater(value_score(self.laptop, lower, score, PREFERENCES), value_score(self.laptop, higher, score, PREFERENCES))

    def test_low_confidence_downgrades_buy_level_offer(self):
        offer = {**self.offer, "price": 1100, "ram_gb": 32, "ssd_gb": 1000, "confidence": "low"}
        offer["price_breakdown"] = effective_price_breakdown(self.laptop, offer, PREFERENCES)
        offer["effective_price"] = offer["price_breakdown"]["effective_price"]
        score = laptop_score(self.laptop, PREFERENCES)
        value = value_score(self.laptop, offer, score, PREFERENCES)
        verdict, reason = decision(self.laptop, offer, score, value)
        self.assertEqual(verdict, "STRONGLY CONSIDER")
        self.assertIn("verification", reason)

    def test_mismatched_configuration_and_missing_price_are_unrated(self):
        score = laptop_score(self.laptop, PREFERENCES)
        self.assertIsNone(value_score(self.laptop, {**self.offer, "configuration_match": "mismatched"}, score, PREFERENCES))
        self.assertEqual(decision(self.laptop, None, score, None)[0], "UNRATED")

    def test_impossible_ram_upgrade_blocks_buy(self):
        laptop = {**self.laptop, "ram_gb": 16, "ram_upgradeable": False}
        offer = {**self.offer, "price": 900, "ram_gb": 16, "ssd_gb": 1000}
        offer["price_breakdown"] = effective_price_breakdown(laptop, offer, PREFERENCES)
        offer["effective_price"] = offer["price_breakdown"]["effective_price"]
        score = laptop_score(laptop, PREFERENCES)
        value = value_score(laptop, offer, score, PREFERENCES)
        self.assertEqual(decision(laptop, offer, score, value)[0], "SKIP")


if __name__ == "__main__":
    unittest.main()
