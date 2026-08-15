import json
import unittest
from pathlib import Path

from tracker.scoring import laptop_score


ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.laptops = json.loads((ROOT / "config" / "laptops.json").read_text(encoding="utf-8"))
        cls.sources = json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8"))
        cls.manual_offers = json.loads((ROOT / "config" / "manual_offers.json").read_text(encoding="utf-8"))
        cls.components = json.loads((ROOT / "config" / "components.json").read_text(encoding="utf-8"))
        cls.preferences = json.loads((ROOT / "config" / "preferences.yaml").read_text(encoding="utf-8"))
        cls.reconciliation = json.loads((ROOT / "config" / "reconciliation_2026-08-15.json").read_text(encoding="utf-8"))
        cls.market_leads = json.loads((ROOT / "config" / "market_leads.json").read_text(encoding="utf-8"))
        cls.ideal = json.loads((ROOT / "config" / "ideal_requirements.json").read_text(encoding="utf-8"))

    def test_master_catalog_has_unique_ids(self):
        ids = [laptop["id"] for laptop in self.laptops]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 50)

    def test_new_galaxus_candidates_update_or_add_exact_skus_without_duplicates(self):
        expected = {
            "83f3003hpb": "lenovo-legion-pro5-83f3003hpb",
            "83lt000mus": "lenovo-legion-pro5-83lt000mus",
            "83lt001wpb": "lenovo-legion-pro5-83lt001wpb",
        }
        for sku, record_id in expected.items():
            matches = [item["id"] for item in self.laptops if (item.get("sku") or "").lower() == sku]
            self.assertEqual(matches, [record_id], sku)

    def test_research_reconciliation_covers_every_supplied_row(self):
        self.assertEqual(self.reconciliation["source_rows"], 47)
        self.assertEqual(len(self.reconciliation["entries"]), 47)
        allowed = {"updated", "replaced_placeholder", "historical_only"}
        self.assertTrue(all(row["action"] in allowed for row in self.reconciliation["entries"]))

    def test_configuration_fingerprints_are_unique(self):
        identities = [(item["brand"].lower(), item["model"].lower(), json.dumps(item.get("configuration_fingerprint"), sort_keys=True)) for item in self.laptops]
        self.assertEqual(len(identities), len(set(identities)))

    def test_vague_placeholders_are_replaced(self):
        ids = {item["id"] for item in self.laptops}
        self.assertNotIn("tulpar-t6-unverified", ids)
        self.assertNotIn("captiva-advanced-gaming-i91-341-unverified", ids)

    def test_marketplace_research_is_dated_unique_and_conflicts_are_rejected(self):
        leads = self.market_leads["leads"]
        self.assertEqual(self.market_leads["as_of"], "2026-08-15")
        self.assertEqual(len(leads), len({item["id"] for item in leads}))
        conflicts = [item for item in leads if item["configuration_status"] == "configuration_conflict_rejected"]
        self.assertTrue(conflicts)
        self.assertTrue(all(item["confidence"] == "low" and item["linked_laptop_id"] is None for item in conflicts))

    def test_copyable_ideal_brief_covers_core_requirements(self):
        text = self.ideal["summary"]
        for phrase in ("32 GB", "1 TB", "RTX 5060", "QWERTY", "Laptop and Value Scores"):
            self.assertIn(phrase, text)
        for section in ("primary_uses", "ideal_configuration", "deal_breakers", "tradeoff_rules", "used_refurbished_checks", "price_guidance", "evaluation_output"):
            self.assertTrue(self.ideal[section], section)

    def test_all_scored_records_reproduce_and_components_resolve(self):
        component_ids = {item["id"] for item in self.components}
        for item in self.laptops:
            self.assertEqual(item.get("laptop_score"), laptop_score(item, self.preferences), item["id"])
            if item.get("cpu") is not None:
                self.assertIn(item.get("cpu_component_id"), component_ids, item["id"])
            if item.get("gpu") is not None:
                self.assertIn(item.get("gpu_profile_id"), component_ids, item["id"])

    def test_every_fixed_source_targets_a_known_laptop(self):
        ids = {laptop["id"] for laptop in self.laptops}
        missing = [source["laptop_id"] for source in self.sources if source.get("type") == "product" and source.get("laptop_id") not in ids]
        missing.extend(source["laptop_id"] for source in self.manual_offers if source.get("enabled") and source.get("laptop_id") not in ids)
        self.assertEqual(missing, [])

    def test_enabled_manual_offers_have_identity_guards(self):
        enabled = [source for source in self.manual_offers if source.get("enabled")]
        self.assertTrue(enabled)
        self.assertTrue(all(source.get("expected_sku") for source in enabled))

    def test_exact_unknowns_remain_null(self):
        by_id = {laptop["id"]: laptop for laptop in self.laptops}
        self.assertIsNone(by_id["acer-nitro-16s-nhu06eg002"]["cpu"])
        self.assertIsNone(by_id["gigabyte-aero-x16-1vh93dec64ah"]["usb_c_pd"])
        self.assertIsNone(by_id["asus-rog-strix-g16-g614fr-s5214w"]["numpad"])

    def test_current_snapshots_are_dated_not_live_offers(self):
        snapshots = [laptop["market_snapshot"] for laptop in self.laptops if laptop.get("market_snapshot")]
        self.assertTrue(snapshots)
        self.assertTrue(all(snapshot["date"] == "2026-08-15" for snapshot in snapshots))


if __name__ == "__main__":
    unittest.main()
