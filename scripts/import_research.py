from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from statistics import median
from typing import Any


SCORE_FIELDS = {
    "gpu": "gpu_22",
    "cpu": "cpu_16",
    "memory_storage": "ram_ssd_expandability_12",
    "cooling_build": "cooling_sustained_build_12",
    "keyboard": "keyboard_12",
    "display": "display_10",
    "battery_usb_c": "battery_usb_c_7",
    "portability": "portability_charger_5",
    "windows_hello": "windows_hello_3",
    "ports_misc": "ports_misc_1",
}

WEIGHTS = {
    "gpu": 22,
    "cpu": 16,
    "memory_storage": 12,
    "cooling_build": 12,
    "keyboard": 12,
    "display": 10,
    "battery_usb_c": 7,
    "portability": 5,
    "windows_hello": 3,
    "ports_misc": 1,
}

# Row numbers in laptop_variants_2026-08-15.csv. Rows 36 and the old fixed
# prebuild observations intentionally consolidate into another master record or
# a historical reference rather than creating a duplicate family record.
ROW_IDS = {
    1: "xmg-core-16-m25-ai7-350-rtx5060",
    2: "xmg-core-16-m25-ai9-365-rtx5060",
    3: "xmg-core-16-m25-hx370-rtx5060",
    4: "xmg-core-16-m25-ai7-350-rtx5070",
    5: "xmg-core-16-m25-ai9-365-rtx5070",
    6: "xmg-core-16-m25-hx370-rtx5070",
    7: "xmg-core-16-ve-m25",
    8: "tuxedo-infinitybook-max16-g10-ai7-350-rtx5060",
    9: "tuxedo-infinitybook-max16-g10-ai9-365-rtx5060",
    10: "tuxedo-infinitybook-max16-g10-hx370-rtx5060",
    11: "tuxedo-infinitybook-max16-g10-ai7-350-rtx5070",
    12: "tuxedo-infinitybook-max16-g10-ai9-365-rtx5070",
    13: "tuxedo-infinitybook-max16-g10-hx370-rtx5070",
    14: "gigabyte-aero-x16-1vh93dec64ah",
    15: "gigabyte-aero-x16-1wh93dec64ah",
    16: "gigabyte-aero-x16-2wha3dec65ap",
    17: "lenovo-legion-pro5-83lt004nge",
    18: "lenovo-legion-pro5-83lt004mge",
    19: "lenovo-legion-pro5-83lt0009ge",
    20: "lenovo-legion-pro5-83f3003hpb",
    21: "asus-tuf-a16-fa608up-rv019w",
    22: "asus-tuf-a16-fa608up-rv124w",
    23: "asus-tuf-a16-fa608um-rv136w",
    24: "asus-v16-v3607vm",
    25: "asus-v16-v3607vp",
    26: "acer-nitro-v16s-anv16s41-nhqzyeg002",
    27: "acer-nitro-v16s-anv16s61-nhqxpeg001",
    28: "acer-nitro-16s-nhqxleg002",
    29: "acer-nitro-16s-nhqxteg002",
    30: "acer-nitro-16s-nhu06eg002",
    31: "asus-rog-strix-g16-g614fr-s5214w",
    32: "msi-vector-16-hx-ai-a2xwhg-074",
    33: "hp-omen-16-ap0192ng",
    34: "hp-omen-16-ap0191ng",
    35: "pcspecialist-ionico-ii-16-config-2026-08",
    36: "pcspecialist-ionico-ii-16-config-2026-08",
    37: "pcspecialist-defiance16-5070ti-target",
    38: "dell-pro-max-16-mc16250",
    39: "dell-pro-max-16-mc16250-4jwk2",
    40: "medion-erazer-defender17-p1-30039763a1",
    41: "asus-zephyrus-g16-ga605km-qr003w",
    42: "gigabyte-gaming-a16-pro-dxhg4decc4sh",
    43: "tulpar-t6-v3-5-1",
    44: "captiva-highend-gaming-i95-052ge",
    45: "lenovo-legion-7i-83kycto1wwnl2",
    46: "lenovo-legion-pro5-83lu0057mh",
    47: "clevo-unresolved-previous-candidate",
}

LEGACY_IDS = {
    "tulpar-t6-v3-5-1": "tulpar-t6-unverified",
    "captiva-highend-gaming-i95-052ge": "captiva-16-gaming-unverified",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def numeric(value: str | None) -> float | None:
    if not value or value.strip().lower() == "unknown":
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", value)
    return float(match.group().replace(",", ".")) if match else None


def integer(value: str | None) -> int | None:
    number = numeric(value)
    return round(number) if number is not None else None


def score_value(value: str | None) -> int | None:
    if not value or not re.fullmatch(r"\d+(?:\.\d+)?", value.strip()):
        return None
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def laptop_score(criteria: dict[str, int | None]) -> int | None:
    if any(criteria.get(key) is None for key in WEIGHTS):
        return None
    total = sum(Decimal(criteria[key]) * Decimal(weight) for key, weight in WEIGHTS.items()) / Decimal(100)
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def aliases(raw: str) -> list[str]:
    if not raw or any(term in raw.lower() for term in ("unknown", "no fixed", "configurator")):
        return []
    return [part.strip() for part in re.split(r"\s*/\s*|\s*;\s*", raw) if part.strip()]


def confidence(raw: str) -> str:
    value = raw.lower()
    if value == "none":
        return "low"
    if "high" in value:
        return "high"
    if "medium" in value:
        return "medium"
    return "low"


def configuration_type(raw: str) -> str:
    value = raw.lower()
    if "fixed" in value:
        return "fixed_sku"
    if "config" in value:
        return "configurable_target"
    if "family" in value or "concept" in value or "identity" in value:
        return "unresolved_reference"
    return "research_variant"


def os_status(raw: str) -> str:
    value = (raw or "").lower()
    if "windows" in value:
        return "windows_included"
    if "no os" in value or "without os" in value:
        return "no_os"
    if "linux" in value or "tuxedo os" in value:
        return "linux"
    if "configur" in value or "select" in value:
        return "selectable"
    return "unknown"


def bool_value(raw: str | None) -> bool | None:
    value = (raw or "").strip().lower()
    if value.startswith("yes"):
        return True
    if value.startswith("no"):
        return False
    return None


def parse_tgp(raw: str | None) -> int | None:
    if not raw or raw.lower() == "unknown":
        return None
    numbers = [int(value) for value in re.findall(r"\d+", raw)]
    if not numbers:
        return None
    if "+" in raw and len(numbers) >= 2 and numbers[0] >= 40 and numbers[1] <= 30:
        return numbers[0] + numbers[1]
    plausible = [value for value in numbers if 35 <= value <= 200]
    return max(plausible) if plausible else None


def parse_storage(raw: str | None) -> int | None:
    if not raw or raw.lower() == "unknown":
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*tb", raw, re.I)
    if match:
        return round(float(match.group(1)) * 1000)
    match = re.search(r"(\d+)\s*gb", raw, re.I)
    return int(match.group(1)) if match else None


def parse_ram(raw: str | None) -> int | None:
    if not raw or raw.lower() == "unknown":
        return None
    match = re.search(r"(\d+)\s*gb", raw, re.I)
    return int(match.group(1)) if match else None


def seed_record(row: dict[str, str], record_id: str) -> dict[str, Any]:
    unresolved = configuration_type(row["variant_type"]) == "unresolved_reference"
    return {
        "id": record_id,
        "brand": row["manufacturer"],
        "model": row["model"],
        "sku": aliases(row["exact_sku_or_product_id"])[0] if aliases(row["exact_sku_or_product_id"]) else None,
        "variant": row["model"],
        "status": "archived" if unresolved or row["priority"] == "3" else "watchlist",
        "cpu": None if row["cpu"].lower() == "unknown" else row["cpu"],
        "cpu_family": None,
        "gpu": None if row["gpu"].lower() == "unknown" else row["gpu"].replace("NVIDIA ", ""),
        "gpu_vram_gb": integer(row["gpu_vram"]),
        "gpu_tgp_w": parse_tgp(row["gpu_tgp"]),
        "ram_gb": parse_ram(row["ram"]),
        "ram_type": None,
        "ram_upgradeable": bool_value(row["ram_replaceable"]),
        "ssd_gb": parse_storage(row["ssd"]),
        "second_m2": bool_value(row["second_m2"]),
        "display_size_in": numeric(row["display"]),
        "resolution": next(iter(re.findall(r"\d{4}\s*[x×]\s*\d{4}", row["display"])), None),
        "aspect_ratio": "16:10" if "16:10" in row["display"] else None,
        "refresh_rate_hz": integer(next(iter(re.findall(r"\d+\s*hz", row["display"], re.I)), "")),
        "panel_type": "OLED" if "oled" in row["display"].lower() else "IPS" if "ips" in row["display"].lower() else None,
        "brightness_nits": integer(next(iter(re.findall(r"\d+\s*nit", row["display"], re.I)), "")),
        "weight_kg": numeric(row["weight_kg"]),
        "battery_wh": numeric(row["battery"]),
        "numpad": bool_value(row["numpad"]),
        "keyboard_layout": None if row["keyboard_layout"].lower() == "unknown" else row["keyboard_layout"],
        "windows_hello": bool_value(row["windows_hello"]),
        "usb_c_pd": bool_value(row["usb_c_charging"]),
        "thunderbolt": True if "thunderbolt" in row["usb_c_charging"].lower() else None,
        "wifi": None,
        "os": None if row["operating_system"].lower() == "unknown" else row["operating_system"],
        "confidence": "low",
        "historical_references": [],
        "market_snapshot": None,
        "target_prices": {},
        "notes": row["notes"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the verified 2026-08-15 research package.")
    parser.add_argument("variants", type=Path)
    parser.add_argument("scores", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    variants = read_csv(args.variants)
    scores = read_csv(args.scores)
    if len(variants) != 47 or len(scores) != 47:
        raise SystemExit("Expected the paired 47-row research exports.")

    config_dir = args.root / "config"
    existing = json.loads((config_dir / "laptops.json").read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in existing}
    reconciliation: list[dict[str, Any]] = []

    for index, (row, score_row) in enumerate(zip(variants, scores, strict=True), start=1):
        if row["manufacturer"].lower() != score_row["manufacturer"].lower():
            raise SystemExit(f"Research row {index} does not align with the score export.")
        target_id = ROW_IDS[index]
        legacy_id = LEGACY_IDS.get(target_id)
        existing_record = by_id.get(target_id) or (by_id.pop(legacy_id, None) if legacy_id else None)
        if index == 36:
            reconciliation.append({"row": index, "source_model": row["model"], "action": "historical_only", "target_id": target_id, "reason": "Same configurable IONICO II family; no exact saved configuration."})
            continue
        if target_id in LEGACY_IDS and existing_record:
            record = seed_record(row, target_id)
            record["historical_references"] = existing_record.get("historical_references", [])
            record["legacy_ids"] = sorted(set(existing_record.get("legacy_ids", []) + [LEGACY_IDS[target_id]]))
        else:
            record = existing_record or seed_record(row, target_id)
        action = "updated" if existing_record else "added"
        if legacy_id and existing_record:
            action = "replaced_placeholder"
            record["legacy_ids"] = sorted(set(record.get("legacy_ids", []) + [legacy_id]))
        record["id"] = target_id
        record["brand"] = row["manufacturer"]
        record["sku_aliases"] = aliases(row["exact_sku_or_product_id"])
        if record["sku_aliases"] and not record.get("sku"):
            record["sku"] = record["sku_aliases"][0]
        record["configuration_type"] = configuration_type(row["variant_type"])
        record["os_status"] = os_status(row["operating_system"])
        record["source_urls"] = [url for url in (row["product_url"], row["spec_url"]) if url and url.lower() != "unknown"]
        record["verification"] = {
            "as_of": row["price_evidence_date"] or "2026-08-15",
            "confidence": confidence(score_row["score_confidence"]),
            "score_confidence": score_row["score_confidence"],
            "sources": record["source_urls"],
            "notes": row["notes"],
        }
        criteria = {name: score_value(score_row[column]) for name, column in SCORE_FIELDS.items()}
        record["criteria_scores"] = criteria
        record["laptop_score"] = laptop_score(criteria)
        record["score_as_of"] = "2026-08-15"
        record["score_confidence"] = score_row["score_confidence"]
        record["regret_flags"] = [value.strip() for value in re.split(r";|\|", score_row["long_term_regret_flags"]) if value.strip() and value.strip().lower() != "none"]
        record["research_value_snapshot"] = {
            "value_score": score_value(score_row["value_score_100"]),
            "rating": score_row["value_rating"] or None,
            "decision": score_row["decision"] or row["verdict"],
            "price_eur": numeric(score_row["current_price_eur"]),
            "date": row["price_evidence_date"] or "2026-08-15",
        }
        targets = {
            "buy_now": numeric(row["target_buy_now_eur"]),
            "strong": numeric(row["target_strong_eur"]),
            "consider": numeric(row["target_consider_eur"]),
        }
        record["target_prices"] = {key: value for key, value in targets.items() if value is not None} or record.get("target_prices", {})
        record["configuration_fingerprint"] = {
            "cpu": record.get("cpu"), "gpu": record.get("gpu"), "gpu_tgp_w": record.get("gpu_tgp_w"),
            "ram_gb": record.get("ram_gb"), "ssd_gb": record.get("ssd_gb"),
            "keyboard_layout": record.get("keyboard_layout"), "os_status": record.get("os_status"),
            "configuration_type": record.get("configuration_type"),
        }
        record.pop("curated_fit_score", None)
        record["notes"] = row["notes"]
        by_id[target_id] = record
        reconciliation.append({"row": index, "source_model": row["model"], "action": action, "target_id": target_id})

    # The six master XMG rows represent saved target configurations with a
    # selectable QWERTY keyboard and OS. The two German AI 9 prebuild rows in
    # the research export are retained as dated history rather than allowed to
    # overwrite those reusable target identities.
    for record_id in (
        "xmg-core-16-m25-ai7-350-rtx5060", "xmg-core-16-m25-ai9-365-rtx5060",
        "xmg-core-16-m25-hx370-rtx5060", "xmg-core-16-m25-ai7-350-rtx5070",
        "xmg-core-16-m25-ai9-365-rtx5070", "xmg-core-16-m25-hx370-rtx5070",
    ):
        record = by_id[record_id]
        record["configuration_type"] = "configurable_target"
        record["keyboard_layout"] = "configurable, including US International"
        record["os_status"] = "selectable"
        record["criteria_scores"]["keyboard"] = 100
        record["laptop_score"] = laptop_score(record["criteria_scores"])
        record["configuration_fingerprint"].update({
            "keyboard_layout": record["keyboard_layout"],
            "os_status": "selectable",
            "configuration_type": "configurable_target",
        })
    for record_id, price, label in (
        ("xmg-core-16-m25-ai9-365-rtx5060", 2149, "Former GameStar XXL AI 9 German prebuild"),
        ("xmg-core-16-m25-ai9-365-rtx5070", 2299, "Former GameStar XXXL AI 9 German prebuild"),
    ):
        history = by_id[record_id].setdefault("historical_references", [])
        reference = {"date": "2026-08-15", "price_eur": price, "label": label}
        if reference not in history:
            history.append(reference)

    # The current Bestware URLs have changed from the dated AI 9 research
    # snapshot to fixed German AI 7 prebuilds. They are separate configurations.
    for gpu, price, suffix, source_url in (
        ("RTX 5060", 2099, "xxl", "https://bestware.com/de/xmg-core-16-m25-gamestar-xxl.html"),
        ("RTX 5070", 2249, "xxxl", "https://bestware.com/de/xmg-core-16-m25-gamestar-xxxl.html"),
    ):
        base_id = f"xmg-core-16-m25-ai7-350-{gpu.lower().replace(' ', '')}"
        base = dict(by_id[base_id])
        record_id = f"xmg-core-16-m25-gamestar-{suffix}-ai7-350-{gpu.lower().replace(' ', '')}-de"
        base.update({
            "id": record_id,
            "variant": f"GameStar {suffix.upper()} / Ryzen AI 7 350 / {gpu} / 32 GB / 1 TB / German prebuild",
            "configuration_type": "fixed_prebuild",
            "keyboard_layout": "DE QWERTZ",
            "os": "Windows 11 Home",
            "os_status": "windows_included",
            "sku_aliases": ["XCO16M25", f"GameStar {suffix.upper()}"],
            "source_urls": [source_url],
            "market_snapshot": {"date": "2026-08-15", "price_eur": price, "label": "Official Bestware live prebuild"},
            "verification": {"as_of": "2026-08-15", "confidence": "verified", "score_confidence": "High", "sources": [source_url], "notes": "Current official prebuild fingerprint; kept separate from configurable QWERTY targets."},
            "confidence": "verified",
            "score_confidence": "High",
            "notes": "Current German fixed prebuild. Do not merge with the configurable QWERTY target configuration.",
        })
        base["criteria_scores"] = dict(base["criteria_scores"])
        base["criteria_scores"]["keyboard"] = 75
        base["laptop_score"] = laptop_score(base["criteria_scores"])
        base["configuration_fingerprint"] = {
            "cpu": base["cpu"], "gpu": base["gpu"], "gpu_tgp_w": base["gpu_tgp_w"],
            "ram_gb": 32, "ssd_gb": 1000, "keyboard_layout": "DE QWERTZ",
            "os_status": "windows_included", "configuration_type": "fixed_prebuild",
        }
        by_id[record_id] = base

    # Reusable component indices are medians of the verified research criterion
    # scores for the same CPU or GPU/TGP profile. Per-laptop criterion scores are
    # retained so chassis-specific evidence is still visible.
    observations: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for record in by_id.values():
        criteria = record.get("criteria_scores") or {}
        if record.get("cpu") and criteria.get("cpu") is not None:
            observations[("cpu", record["cpu"])].append((criteria["cpu"], record))
        if record.get("gpu") and criteria.get("gpu") is not None:
            profile = f"{record['gpu']} | {record.get('gpu_vram_gb') or 'unknown'} GB | {record.get('gpu_tgp_w') or 'unknown'} W"
            observations[("gpu", profile)].append((criteria["gpu"], record))

    components = []
    component_ids: dict[tuple[str, str], str] = {}
    for (kind, name), values in sorted(observations.items()):
        component_id = f"{kind}-{slug(name)}"
        component_ids[(kind, name)] = component_id
        sources = sorted({url for _, record in values for url in record.get("source_urls", [])})
        components.append({
            "id": component_id, "type": kind, "name": name,
            "comparison_score": int(Decimal(str(median(score for score, _ in values))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "confidence": max((record.get("confidence", "low") for _, record in values), key=lambda value: {"low": 1, "medium": 2, "high": 3, "verified": 4}.get(value, 1)),
            "as_of": "2026-08-15", "sources": sources,
            "notes": "Normalized comparison index from the fixed personal scoring rubric; not a universal benchmark percentage.",
        })

    for record in by_id.values():
        record["cpu_component_id"] = component_ids.get(("cpu", record.get("cpu")))
        if record.get("gpu"):
            profile = f"{record['gpu']} | {record.get('gpu_vram_gb') or 'unknown'} GB | {record.get('gpu_tgp_w') or 'unknown'} W"
            record["gpu_profile_id"] = component_ids.get(("gpu", profile))
        else:
            record["gpu_profile_id"] = None

    order = {item["id"]: index for index, item in enumerate(existing)}
    laptops = sorted(by_id.values(), key=lambda item: (order.get(item["id"], 10_000), item["brand"], item["model"], item["id"]))
    write_json(config_dir / "laptops.json", laptops)
    write_json(config_dir / "components.json", components)
    write_json(config_dir / "reconciliation_2026-08-15.json", {
        "source_rows": 47,
        "master_records": len(laptops),
        "generated_from": [args.variants.name, args.scores.name],
        "entries": reconciliation,
        "derived_current_records": [
            "xmg-core-16-m25-gamestar-xxl-ai7-350-rtx5060-de",
            "xmg-core-16-m25-gamestar-xxxl-ai7-350-rtx5070-de",
        ],
    })


if __name__ == "__main__":
    main()
