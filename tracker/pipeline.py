from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tracker.models import Offer, SourceHealth
from tracker.scoring import compare_to_reference, decision, effective_price_breakdown, laptop_score, value_rating, value_score
from tracker.sources import run_source
from tracker.utils import now_iso, read_json, write_json


def load_preferences(path: Path) -> dict[str, Any]:
    # JSON is valid YAML; this keeps V1 dependency-free while retaining preferences.yaml.
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_offer(previous: dict[str, Any] | None, current: Offer, timestamp: str) -> dict[str, Any]:
    value = current.to_dict()
    value["first_seen"] = previous.get("first_seen") if previous else timestamp
    value["last_seen"] = timestamp if current.availability not in {"out_of_stock", "listing_removed"} else previous.get("last_seen") if previous else timestamp
    return value


def _mark_missing(previous_offers: list[dict[str, Any]], current: dict[str, dict[str, Any]], successful_sources: set[str], successful_source_ids: set[str], invalidated_source_ids: set[str], timestamp: str) -> None:
    for old in previous_offers:
        if old["id"] in current:
            continue
        if old.get("source_id") in invalidated_source_ids:
            old = dict(old)
            old["availability"] = "listing_removed"
            old["last_checked"] = timestamp
            old["notes"] = "The retailer page changed configuration; this observation was invalidated."
            current[old["id"]] = old
            continue
        source_succeeded = old.get("source_id") in successful_source_ids if old.get("source_id") else old.get("source") in successful_sources
        if not source_succeeded:
            current[old["id"]] = old
            continue
        missed = int(old.get("missed_checks") or 0) + 1
        old = dict(old)
        old["missed_checks"] = missed
        old["last_checked"] = timestamp
        if missed >= 2:
            old["availability"] = "listing_removed"
        current[old["id"]] = old


def _history_event(previous: dict[str, Any] | None, current: dict[str, Any], timestamp: str) -> dict[str, Any] | None:
    fields = ("price", "shipping", "total_price", "availability")
    if previous and all(previous.get(field) == current.get(field) for field in fields):
        return None
    return {"offer_id": current["id"], "laptop_id": current["laptop_id"], "timestamp": timestamp, **{field: current.get(field) for field in fields}}


def _history_stats(events: list[dict[str, Any]], laptop_id: str) -> dict[str, Any]:
    values = [event.get("total_price") for event in events if event.get("laptop_id") == laptop_id and event.get("total_price") is not None]
    if not values:
        return {"lowest": None, "highest": None, "average": None, "observations": 0}
    return {"lowest": min(values), "highest": max(values), "average": round(sum(values) / len(values), 2), "observations": len(values)}


def _read_history(root: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in sorted((root / "history").glob("*.jsonl")) if (root / "history").exists() else []:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


def _canonical_laptop_id(candidate: dict[str, Any], known: dict[str, dict[str, Any]]) -> str:
    brand = (candidate.get("brand") or "").lower()
    sku = (candidate.get("sku") or "").lower()
    model = (candidate.get("model") or "").lower()
    normalized_model = "".join(part for part in model.split("(")[0] if part.isalnum())
    exact_matches: list[str] = []
    for laptop in known.values():
        if (laptop.get("brand") or "").lower() != brand:
            continue
        known_sku = (laptop.get("sku") or "").lower()
        known_model = (laptop.get("model") or "").lower()
        normalized_known_model = "".join(part for part in known_model.split("(")[0] if part.isalnum())
        if sku and known_sku and sku == known_sku and normalized_model == normalized_known_model:
            exact_matches.append(laptop["id"])
    if len(exact_matches) == 1:
        return exact_matches[0]
    return candidate["id"]


def _append_events(output: Path, previous: Path, events: list[dict[str, Any]], timestamp: str) -> None:
    history_dir = output / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    month = timestamp[:7]
    target = history_dir / f"{month}.jsonl"
    with target.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def run_pipeline(project_root: Path, output: Path, previous: Path | None = None, mode: str = "all", offline: bool = False) -> dict[str, Any]:
    timestamp = now_iso()
    previous = previous or Path("__missing__")
    if output.exists():
        shutil.rmtree(output)
    if previous.exists():
        shutil.copytree(previous, output)
    else:
        output.mkdir(parents=True)

    preferences = load_preferences(project_root / "config" / "preferences.yaml")
    seeded = read_json(project_root / "config" / "laptops.json", [])
    laptop_map = {item["id"]: item for item in seeded}
    family_members: set[str] = set()
    for family in read_json(project_root / "config" / "families.json", []):
        for laptop_id in family.get("members", []):
            if laptop_id not in laptop_map:
                raise ValueError(f"Unknown laptop {laptop_id} in family {family['id']}")
            if laptop_id in family_members:
                raise ValueError(f"Laptop {laptop_id} belongs to more than one family")
            family_members.add(laptop_id)
            laptop_map[laptop_id] = {
                **laptop_map[laptop_id],
                "family_id": family["id"],
                "family_label": family["label"],
            }
    previous_laptops = read_json(previous / "laptops.json", []) if previous.exists() else []
    retired_ids = set(read_json(project_root / "config" / "identity_migrations.json", {}).keys())
    for laptop in previous_laptops:
        if laptop["id"] in retired_ids:
            continue
        laptop_map.setdefault(laptop["id"], laptop)
    previous_offers = read_json(previous / "offers.json", []) if previous.exists() else []
    previous_offer_map = {offer["id"]: offer for offer in previous_offers}
    cache = read_json(previous / "cache.json", {}) if previous.exists() else {}
    sources = read_json(project_root / "config" / "sources.json", []) + read_json(project_root / "config" / "manual_offers.json", [])
    active_sources = [source for source in sources if source.get("enabled")]
    if mode == "watchlist":
        active_sources = [source for source in active_sources if source.get("type", "product") != "catalog"]
    elif mode == "discovery":
        active_sources = [source for source in active_sources if source.get("type") == "catalog"]

    current: dict[str, dict[str, Any]] = {}
    health: list[dict[str, Any]] = []
    successful_sources: set[str] = set()
    successful_source_ids: set[str] = set()
    invalidated_source_ids: set[str] = set()
    for source in active_sources:
        source = dict(source)
        target_laptop = laptop_map.get(source.get("laptop_id"))
        if target_laptop and not source.get("requires_saved_configuration") and not source.get("expected_fingerprint"):
            source["expected_fingerprint"] = {
                "cpu": target_laptop.get("cpu"),
                "gpu": target_laptop.get("gpu"),
                "ram_gb": target_laptop.get("ram_gb"),
                "ssd_gb": target_laptop.get("ssd_gb"),
                "os_status": target_laptop.get("os_status", "unknown"),
            }
        if offline:
            source_health = SourceHealth(
                id=source["id"], source=source["source"], url=source["url"], status="offline_fixture",
                last_attempt=timestamp, last_success=None, offers_found=0,
            )
            health.append(source_health.to_dict())
            continue
        result, cache_entry = run_source(source, cache.get(source["id"]))
        cache[source["id"]] = cache_entry
        health.append(result.health.to_dict() if result.health else {})
        if result.health and result.health.status in {"ok", "not_modified"}:
            successful_sources.add(source["source"])
            successful_source_ids.add(source["id"])
        if result.health and result.health.status == "configuration_changed":
            invalidated_source_ids.add(source["id"])
        discovered_id_map: dict[str, str] = {}
        for laptop in result.discovered_laptops:
            canonical_id = _canonical_laptop_id(laptop, laptop_map)
            discovered_id_map[laptop["id"]] = canonical_id
            if canonical_id == laptop["id"]:
                prior = laptop_map.get(laptop["id"])
                laptop["first_seen"] = prior.get("first_seen") if prior else timestamp
                laptop["last_seen"] = timestamp
                laptop_map[laptop["id"]] = {**(prior or {}), **laptop}
        for offer in result.offers:
            offer.laptop_id = discovered_id_map.get(offer.laptop_id, offer.laptop_id)
            current[offer.id] = _merge_offer(previous_offer_map.get(offer.id), offer, timestamp)

    # Successful source runs may age out listings, while failed or unexecuted
    # sources leave their previous offers untouched.
    _mark_missing(previous_offers, current, successful_sources, successful_source_ids, invalidated_source_ids, timestamp)
    offers = sorted(current.values(), key=lambda item: (item["laptop_id"], item["seller"], item["id"]))

    new_events = []
    for offer in offers:
        event = _history_event(previous_offer_map.get(offer["id"]), offer, timestamp)
        if event:
            new_events.append(event)
    _append_events(output, previous, new_events, timestamp)
    all_events = _read_history(output)

    by_laptop: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for offer in offers:
        by_laptop[offer["laptop_id"]].append(offer)
    reference = laptop_map[preferences["reference_laptop_id"]]
    rows: list[dict[str, Any]] = []
    row_map: dict[str, dict[str, Any]] = {}
    for laptop in laptop_map.values():
        score = laptop_score(laptop, preferences)
        laptop_offers = by_laptop.get(laptop["id"], [])
        for offer in laptop_offers:
            breakdown = effective_price_breakdown(laptop, offer, preferences)
            offer["price_breakdown"] = breakdown
            offer["effective_price"] = breakdown["effective_price"] if breakdown else None
            offer["value_score"] = value_score(laptop, offer, score, preferences)
            offer["value_rating"] = value_rating(offer["value_score"])
        available = [
            offer for offer in laptop_offers
            if offer.get("effective_price") is not None
            and offer.get("availability") not in {"out_of_stock", "listing_removed"}
            and offer.get("configuration_match") not in {"mismatched", "unidentified"}
        ]
        best_offer = max(available, key=lambda offer: (offer.get("value_score") is not None, offer.get("value_score") or -1, -(offer.get("effective_price") or 0))) if available else None
        value = best_offer.get("value_score") if best_offer else None
        verdict, reason = decision(laptop, best_offer, score, value)
        rows.append({
            **laptop,
            "laptop_score": score,
            "value_score": value,
            "value_rating": value_rating(value),
            "decision": verdict,
            "decision_reason": reason,
            "best_offer": best_offer,
            "offers": laptop_offers,
            "history": _history_stats(all_events, laptop["id"]),
            "comparison_to_xmg": [],
        })
        row_map[laptop["id"]] = rows[-1]
    reference_row = row_map[reference["id"]]
    reference_price = reference_row.get("best_offer", {}).get("effective_price") if reference_row.get("best_offer") else None
    for row in rows:
        row["comparison_to_xmg"] = compare_to_reference(
            row, row.get("best_offer", {}).get("effective_price") if row.get("best_offer") else None,
            reference, reference_price,
        )
    rows.sort(key=lambda item: (item["value_score"] is not None, item["value_score"] or -1, item["laptop_score"] or -1), reverse=True)

    cutoff = datetime.now(UTC).timestamp() - 24 * 3600
    recent_events = [event for event in all_events if datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).timestamp() >= cutoff]
    price_drops = 0
    for event in recent_events:
        previous_events = [old for old in all_events if old["offer_id"] == event["offer_id"] and old["timestamp"] < event["timestamp"] and old.get("total_price") is not None]
        if previous_events and event.get("total_price") is not None and event["total_price"] < previous_events[-1]["total_price"]:
            price_drops += 1
    dashboard = {
        "schema_version": 2,
        "generated_at": timestamp,
        "mode": mode,
        "purchase_completed": read_json(previous / "purchase.json", None) if previous.exists() else None,
        "summary": {
            "major_deals": sum(1 for row in rows if row["decision"] == "BUY NOW"),
            "price_drops_24h": price_drops,
            "new_models_24h": sum(
                1 for row in rows
                if row["status"] == "discovered" and row.get("first_seen")
                and datetime.fromisoformat(row["first_seen"].replace("Z", "+00:00")).timestamp() >= cutoff
            ),
            "tracked_laptops": len(rows),
            "active_offers": len([offer for offer in offers if offer.get("availability") not in {"out_of_stock", "listing_removed"}]),
        },
        "preferences": preferences,
        "components": read_json(project_root / "config" / "components.json", []),
        "ideal_requirements": read_json(project_root / "config" / "ideal_requirements.json", {}),
        "market_leads": read_json(project_root / "config" / "market_leads.json", {}),
        "laptops": rows,
        "source_health": health or read_json(previous / "source_health.json", []),
        "recent_events": recent_events[-100:],
    }
    write_json(output / "dashboard.json", dashboard)
    write_json(output / "laptops.json", list(laptop_map.values()))
    write_json(output / "offers.json", offers)
    write_json(output / "source_health.json", dashboard["source_health"])
    write_json(output / "cache.json", cache)
    run_entry = {
        "timestamp": timestamp,
        "mode": mode,
        "sources_checked": len(active_sources),
        "successful": sum(1 for item in health if item.get("status") in {"ok", "not_modified", "offline_fixture"}),
        "failed": sum(1 for item in health if item.get("status") in {"failed", "cooldown"}),
        "offers": len(offers),
        "price_changes": len(new_events),
        "new_models": sum(1 for row in rows if row["status"] == "discovered"),
        "strong_deals": dashboard["summary"]["major_deals"],
    }
    with (output / "run_log.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(run_entry, separators=(",", ":")) + "\n")
    return dashboard
