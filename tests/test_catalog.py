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
        cls.families = json.loads((ROOT / "config" / "families.json").read_text(encoding="utf-8"))
        cls.previous_shortlist = json.loads((ROOT / "config" / "reconciliation_previous_shortlist_2026-08-15.json").read_text(encoding="utf-8"))
        cls.purchase = json.loads((ROOT / "config" / "purchase.json").read_text(encoding="utf-8"))

    def test_master_catalog_has_unique_ids(self):
        ids = [laptop["id"] for laptop in self.laptops]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 51)

    def test_completed_purchase_matches_catalog_and_price_breakdown(self):
        purchase = self.purchase
        known = {item["id"] for item in self.laptops}
        self.assertEqual(purchase["status"], "completed")
        self.assertIn(purchase["laptop_id"], known)
        self.assertEqual(purchase["configuration"]["storage"], "2 TB WD_BLACK SN7100 PCIe 4.0 x4 NVMe SSD")
        self.assertEqual(purchase["configuration"]["keyboard"], "US International (ISO)")
        pricing = purchase["pricing"]
        self.assertAlmostEqual(pricing["original_configured_price"] * 0.8, pricing["price_after_campaign_discount"], places=2)
        self.assertAlmostEqual(pricing["price_after_campaign_discount"] - pricing["additional_product_discounts"] + pricing["shipping"] - pricing["shipping_discount"], purchase["price"], places=2)
        self.assertAlmostEqual(pricing["original_configured_price"] - purchase["price"], pricing["total_savings"], places=2)

    def test_explicit_families_are_safe_and_zephyrus_variants_remain_exact(self):
        known = {item["id"] for item in self.laptops}
        members = [member for family in self.families for member in family["members"]]
        self.assertEqual(len(members), len(set(members)))
        self.assertTrue(set(members) <= known)
        zephyrus = next(family for family in self.families if family["id"] == "asus-rog-zephyrus-g16-ga605-2025")
        self.assertEqual(set(zephyrus["members"]), {"asus-zephyrus-g16-ga605km-qr003w", "asus-zephyrus-g16-ga605kp-qr022w"})
        self.assertNotIn("xmg-core-16-m25-ve", next(family for family in self.families if family["id"] == "xmg-core-16-m25")["members"])

    def test_new_zephyrus_exact_sku_is_unique(self):
        matches = [item for item in self.laptops if item.get("sku") == "GA605KP-QR022W"]
        self.assertEqual([item["id"] for item in matches], ["asus-zephyrus-g16-ga605kp-qr022w"])
        self.assertEqual(matches[0]["ram_gb"], 32)
        self.assertEqual(matches[0]["gpu_tgp_w"], 105)

    def test_previous_shortlist_is_fully_reconciled_without_missing_records(self):
        known = {item["id"] for item in self.laptops}
        self.assertEqual(self.previous_shortlist["source_models"], 20)
        self.assertEqual(len(self.previous_shortlist["entries"]), 20)
        referenced = [record_id for entry in self.previous_shortlist["entries"] for record_id in entry["record_ids"]]
        self.assertTrue(set(referenced) <= known)
        for sku in ("83LU0057MH", "83KYCTO1WWNL2", "DXHG4DECC4SH"):
            self.assertEqual(sum(item.get("sku") == sku for item in self.laptops), 1, sku)
        by_sku = {item.get("sku"): item for item in self.laptops}
        self.assertEqual((by_sku["83LU0057MH"]["cpu"], by_sku["83LU0057MH"]["gpu_tgp_w"], by_sku["83LU0057MH"]["laptop_score"]), ("Core Ultra 9 275HX", 140, 89))
        self.assertEqual((by_sku["83KYCTO1WWNL2"]["keyboard_layout"], by_sku["83KYCTO1WWNL2"]["windows_hello"], by_sku["83KYCTO1WWNL2"]["laptop_score"]), ("English EU QWERTY", True, 92))
        self.assertEqual((by_sku["DXHG4DECC4SH"]["ram_gb"], by_sku["DXHG4DECC4SH"]["ssd_gb"], by_sku["DXHG4DECC4SH"]["gpu_tgp_w"]), (32, 1000, None))
        retired = {"lenovo-legion-7i-gen10-unverified", "lenovo-legion-pro5-intel-5070ti-nl-unverified", "pcspecialist-defiance16-unverified"}
        self.assertFalse(retired & known)

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
