from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3, "verified": 4}
DEFAULT_WEIGHTS = {
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


def _round(value: float | Decimal) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def laptop_score(laptop: dict[str, Any], preferences: dict[str, Any]) -> int | None:
    if laptop.get("configuration_type") == "unresolved_reference":
        return None
    criteria = laptop.get("criteria_scores") or {}
    weights = preferences.get("score_weights") or DEFAULT_WEIGHTS
    if any(criteria.get(key) is None for key in weights):
        return None
    total = sum(Decimal(str(criteria[key])) * Decimal(str(weight)) for key, weight in weights.items())
    divisor = sum(Decimal(str(weight)) for weight in weights.values())
    return max(0, min(100, _round(total / divisor)))


def _allowances(preferences: dict[str, Any]) -> dict[str, float]:
    values = preferences.get("cost_allowances") or {}
    return {
        "windows": float(values.get("windows", 50)),
        "ram_32gb": float(values.get("ram_32gb", 90)),
        "ssd_1tb": float(values.get("ssd_1tb", 70)),
    }


def effective_price_breakdown(laptop: dict[str, Any], offer: dict[str, Any], preferences: dict[str, Any]) -> dict[str, Any] | None:
    listing = offer.get("price")
    shipping = offer.get("shipping") or 0
    if listing is None:
        total = offer.get("total_price")
        if total is None:
            return None
        listing, shipping = total, 0
    allowances = _allowances(preferences)
    offer_os = offer.get("os_status") or laptop.get("os_status") or "unknown"
    windows_cost = 0 if offer_os == "windows_included" else allowances["windows"]

    ram_gb = offer.get("ram_gb") if offer.get("ram_gb") is not None else laptop.get("ram_gb")
    ram_cost = 0.0
    feasible = True
    blockers: list[str] = []
    if ram_gb is None:
        blockers.append("RAM capacity is unknown")
    elif ram_gb < preferences["memory"]["minimum_ram_gb"]:
        if laptop.get("ram_upgradeable") is True:
            ram_cost = allowances["ram_32gb"]
        else:
            feasible = False
            blockers.append("RAM cannot reach 32 GB")

    ssd_gb = offer.get("ssd_gb") if offer.get("ssd_gb") is not None else laptop.get("ssd_gb")
    ssd_cost = 0.0
    if ssd_gb is None:
        blockers.append("Storage capacity is unknown")
    elif ssd_gb < preferences["memory"]["minimum_storage_gb"]:
        if laptop.get("ssd_upgradeable", True) is not False:
            ssd_cost = allowances["ssd_1tb"]
        else:
            feasible = False
            blockers.append("Storage cannot reach 1 TB")

    effective = round(float(listing) + float(shipping) + windows_cost + ram_cost + ssd_cost, 2)
    return {
        "listing_price": round(float(listing), 2),
        "shipping": round(float(shipping), 2),
        "windows": windows_cost,
        "ram": ram_cost,
        "ssd": ssd_cost,
        "effective_price": effective,
        "os_status": offer_os,
        "upgrade_feasible": feasible,
        "blockers": blockers,
        "assumptions": [
            label for cost, label in (
                (windows_cost, f"Windows allowance €{_round(windows_cost)}"),
                (ram_cost, f"32 GB RAM allowance €{_round(ram_cost)}"),
                (ssd_cost, f"1 TB SSD allowance €{_round(ssd_cost)}"),
            ) if cost
        ],
    }


def _targets(laptop: dict[str, Any], score: int, condition: str) -> dict[str, float]:
    configured = laptop.get("target_prices") or {}
    consider = configured.get("consider")
    strong = configured.get("strong")
    buy = configured.get("buy_now")
    if consider is None:
        consider = max(1200, min(2300, 1800 * score / 85))
    if strong is None:
        strong = consider * 0.9
    if buy is None:
        buy = consider * 0.82
    multiplier = {"new": 1.0, "open_box": 0.9, "refurbished": 0.8, "used": 0.65}.get(condition, 1.0)
    return {"buy_now": float(buy) * multiplier, "strong": float(strong) * multiplier, "consider": float(consider) * multiplier}


def _interpolate(value: float, low_x: float, high_x: float, low_y: float, high_y: float) -> float:
    if high_x <= low_x:
        return high_y
    position = max(0.0, min(1.0, (value - low_x) / (high_x - low_x)))
    return low_y + (high_y - low_y) * position


def value_score(laptop: dict[str, Any], offer: dict[str, Any] | None, score: int | None, preferences: dict[str, Any]) -> int | None:
    if not offer or score is None:
        return None
    if offer.get("configuration_match") in {"mismatched", "unidentified"}:
        return None
    breakdown = offer.get("price_breakdown") or effective_price_breakdown(laptop, offer, preferences)
    if not breakdown:
        return None
    price = breakdown["effective_price"]
    targets = _targets(laptop, score, offer.get("condition", "new"))
    buy, strong, consider = targets["buy_now"], targets["strong"], targets["consider"]
    if price <= buy:
        base = 95 + min(5, max(0, (buy - price) / max(buy, 1) * 25))
    elif price <= strong:
        base = _interpolate(price, buy, strong, 95, 90)
    elif price <= consider:
        base = _interpolate(price, strong, consider, 90, 80)
    elif price <= consider * 1.25:
        base = _interpolate(price, consider, consider * 1.25, 80, 50)
    else:
        base = _interpolate(price, consider * 1.25, consider * 1.75, 50, 0)
    confidence_value = min(
        CONFIDENCE_RANK.get(laptop.get("confidence", "low"), 1),
        CONFIDENCE_RANK.get(offer.get("confidence", "low"), 1),
    )
    base -= 3 if confidence_value == 2 else 8 if confidence_value == 1 else 0
    return max(0, min(100, _round(base)))


def value_rating(score: int | None) -> str:
    if score is None:
        return "UNRATED"
    if score >= 95:
        return "EXCEPTIONAL"
    if score >= 90:
        return "EXCELLENT"
    if score >= 85:
        return "VERY GOOD"
    if score >= 80:
        return "GOOD"
    if score >= 75:
        return "FAIR"
    if score >= 70:
        return "EXPENSIVE"
    return "POOR VALUE"


def confidence_allows_buy(laptop: dict[str, Any], offer: dict[str, Any] | None) -> bool:
    if not offer or offer.get("effective_price") is None:
        return False
    exact_identity = laptop.get("configuration_type") != "unresolved_reference"
    laptop_confidence = CONFIDENCE_RANK.get(laptop.get("confidence", "low"), 1)
    offer_confidence = CONFIDENCE_RANK.get(offer.get("confidence", "low"), 1)
    critical_known = all(laptop.get(key) is not None for key in ("cpu", "gpu", "ram_gb", "ssd_gb"))
    breakdown = offer.get("price_breakdown") or {}
    return (
        exact_identity and laptop_confidence >= 3 and offer_confidence >= 3
        and critical_known and breakdown.get("upgrade_feasible", False)
        and offer.get("configuration_match") == "matched"
    )


def decision(laptop: dict[str, Any], offer: dict[str, Any] | None, score: int | None, value: int | None) -> tuple[str, str]:
    if value is None or offer is None:
        return "UNRATED", "No current price is attached to a reliably identified configuration."
    breakdown = offer.get("price_breakdown") or {}
    if not breakdown.get("upgrade_feasible", True):
        return "SKIP", "The configuration cannot reach the minimum RAM or storage requirement."
    if value >= 90 and (score or 0) >= 75:
        if confidence_allows_buy(laptop, offer):
            return "BUY NOW", "Excellent effective price, strong laptop fit, and a verified exact configuration."
        return "STRONGLY CONSIDER", "The price is excellent, but verification or upgrade assumptions still need a final check."
    if value >= 82:
        return "STRONGLY CONSIDER", "Strong value after Windows and required upgrade costs are included."
    if value >= 70:
        return "WAIT", "The laptop may fit well, but the effective price is not compelling enough yet."
    return "SKIP", "The effective price does not compensate for this configuration's compromises."


def compare_to_reference(laptop: dict[str, Any], price: float | None, reference: dict[str, Any], reference_price: float | None) -> list[str]:
    if laptop["id"] == reference["id"]:
        return ["Primary reference laptop"]
    result: list[str] = []
    if price is not None and reference_price is not None:
        difference = round(abs(price - reference_price))
        result.append(f"€{difference} {'cheaper' if price < reference_price else 'more expensive'} effective price")
    else:
        result.append("Effective price comparison unavailable")
    for key, label, unit in (("weight_kg", "weight", "kg"), ("gpu_tgp_w", "GPU power", "W")):
        value, ref_value = laptop.get(key), reference.get(key)
        if value is not None and ref_value is not None and value != ref_value:
            diff = round(abs(value - ref_value), 2)
            direction = "lighter" if key == "weight_kg" and value < ref_value else "heavier" if key == "weight_kg" else "lower" if value < ref_value else "higher"
            result.append(f"{diff}{unit} {direction} {label}")
    if laptop.get("numpad") is not None and laptop.get("numpad") != reference.get("numpad"):
        result.append("has numpad" if laptop.get("numpad") else "no numpad")
    if laptop.get("resolution") and reference.get("resolution"):
        result.append("same resolution" if laptop["resolution"] == reference["resolution"] else "different resolution")
    return result[:5]


# Temporary compatibility aliases for callers outside the generated dashboard.
fit_score = laptop_score
deal_score = value_score
deal_tier = value_rating
