from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from tracker.models import Offer, SourceHealth, SourceResult
from tracker.utils import now_iso, number, slugify, stable_id


class JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_json_ld = False
        self.buffer: list[str] = []
        self.documents: list[Any] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.lower() == "script" and "ld+json" in (attributes.get("type") or "").lower():
            self.in_json_ld = True
            self.buffer = []

    def handle_data(self, data: str) -> None:
        if self.in_json_ld:
            self.buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.in_json_ld:
            self.in_json_ld = False
            raw = "".join(self.buffer).strip()
            if raw:
                try:
                    self.documents.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _products(html: str) -> list[dict[str, Any]]:
    parser = JsonLdParser()
    parser.feed(html)
    products: list[dict[str, Any]] = []
    for document in parser.documents:
        for item in _walk(document):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if "Product" in types and item.get("name"):
                products.append(item)
    return products


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _bestware_catalog_products(html: str, base_url: str) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for block in re.findall(r"<product-card\b[^>]*>(.*?)</product-card>", html, flags=re.I | re.S):
        title_match = re.search(r'class="product-card-title"[^>]*>(.*?)</a>', block, flags=re.I | re.S)
        vendor_match = re.search(r'class="product-card-vendor"[^>]*>.*?<a[^>]*>(.*?)</a>', block, flags=re.I | re.S)
        canonical_url_match = re.search(r'data-product-url="([^"]+)"', block, flags=re.I | re.S)
        url_match = canonical_url_match or re.search(r'<a\s+href="([^"]+)"[^>]*class="product-card-title"', block, flags=re.I | re.S)
        price_match = re.search(r'class="amount\s*"[^>]*>(.*?)</span>', block, flags=re.I | re.S)
        if not title_match or not url_match:
            continue
        title = _text(title_match.group(1))
        sku_match = re.search(r"\(([A-Z]\d{2})\)", title)
        features = " ".join(_text(value) for value in re.findall(r'<div class="feature"><span>(.*?)</span>', block, flags=re.I | re.S))
        products.append({
            "@type": "Product",
            "name": f"{title} {features}".strip(),
            "model": title,
            "sku": sku_match.group(1) if sku_match else None,
            "brand": {"name": _text(vendor_match.group(1)) if vendor_match else "XMG"},
            "url": urljoin(base_url, unescape(url_match.group(1))),
            "offers": {
                "price": _text(price_match.group(1)) if price_match else None,
                "priceCurrency": "EUR",
                "availability": "unknown",
                "url": urljoin(base_url, unescape(url_match.group(1))),
            },
        })
    return products


def _offer_block(product: dict[str, Any]) -> dict[str, Any]:
    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = next((offer for offer in offers if isinstance(offer, dict)), {})
    if not isinstance(offers, dict):
        return {}
    return offers


def _availability(value: Any) -> str:
    text = str(value or "").lower()
    if "instock" in text or "in_stock" in text:
        return "in_stock"
    if "outofstock" in text or "out_of_stock" in text:
        return "out_of_stock"
    if "preorder" in text:
        return "preorder"
    return "unknown"


def _configuration_match(html: str, source: dict[str, Any]) -> tuple[str, list[str]]:
    expected = source.get("expected_fingerprint") or {}
    if not expected and not source.get("expected_sku"):
        return "unverified", []
    normalized = re.sub(r"\s+", " ", _text(html)).lower().replace("™", "").replace("®", "")
    missing: list[str] = []
    mismatched: list[str] = []
    expected_sku = str(source.get("expected_sku") or "").lower()
    if expected_sku and expected_sku not in normalized:
        missing.append(f"SKU {source['expected_sku']}")
    for key, value in expected.items():
        if value is None or value == "unknown":
            continue
        if key == "ram_gb":
            found = bool(re.search(rf"\b{int(value)}\s*gb\b", normalized))
            label = f"{int(value)} GB RAM"
        elif key == "ssd_gb":
            expected_tb = float(value) / 1000
            found = bool(re.search(rf"\b{expected_tb:g}\s*tb\b", normalized)) or bool(re.search(rf"\b{int(value)}\s*gb\b", normalized))
            label = f"{expected_tb:g} TB SSD"
        elif key == "os_status":
            found = "windows 11" in normalized if value == "windows_included" else True
            label = "Windows 11"
        else:
            token = str(value).lower().replace("nvidia ", "").replace("amd ", "").replace("intel ", "")
            found = token in normalized
            label = str(value)
        if not found:
            competing = False
            if key == "cpu":
                competing = bool(re.search(r"(?:ryzen (?:ai )?\d[^|,;]{0,24}|core (?:ultra )?[579][^|,;]{0,20})", normalized))
            elif key == "gpu":
                competing = bool(re.search(r"rtx\s*(?:pro\s*)?\d{3,4}(?:\s*ti)?", normalized))
            (mismatched if competing else missing).append(label)
    if mismatched:
        return "mismatched", mismatched
    if missing:
        return "unidentified", missing
    return "matched", []


def _infer_laptop(product: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    title = str(product.get("name") or "Unknown laptop")
    model_name = str(product.get("model") or title)
    sku = product.get("sku") or product.get("mpn")
    brand_value = product.get("brand")
    brand = brand_value.get("name") if isinstance(brand_value, dict) else brand_value
    brand = str(brand or title.split()[0])
    laptop_id = slugify(f"{brand}-{model_name}-{sku or ''}")
    gpu_match = re.search(r"RTX\s*50(?:60|70(?:\s*Ti)?|80)", title, re.I)
    ram_match = re.search(r"(16|32|64|96|128)\s*GB", title, re.I)
    ssd_match = re.search(r"(1|2|4|8)\s*TB", title, re.I)
    return {
        "id": laptop_id,
        "brand": brand,
        "model": model_name,
        "sku": str(sku) if sku else None,
        "variant": title,
        "status": "discovered",
        "cpu": None,
        "cpu_family": None,
        "gpu": gpu_match.group(0).upper().replace("RTX", "RTX ").replace("  ", " ") if gpu_match else None,
        "gpu_vram_gb": None,
        "gpu_tgp_w": None,
        "ram_gb": int(ram_match.group(1)) if ram_match else None,
        "ram_type": None,
        "ram_upgradeable": None,
        "ssd_gb": int(ssd_match.group(1)) * 1000 if ssd_match else None,
        "second_m2": None,
        "display_size_in": None,
        "resolution": None,
        "aspect_ratio": None,
        "refresh_rate_hz": None,
        "panel_type": None,
        "brightness_nits": None,
        "weight_kg": None,
        "battery_wh": None,
        "numpad": None,
        "keyboard_layout": None,
        "windows_hello": None,
        "usb_c_pd": None,
        "thunderbolt": None,
        "wifi": None,
        "os": None,
        "confidence": "low",
        "historical_references": [],
        "target_prices": {},
        "notes": f"Automatically discovered from {source['seller']}; specifications require verification."
    }


def run_source(source: dict[str, Any], cache_entry: dict[str, Any] | None = None, timeout: int = 18) -> tuple[SourceResult, dict[str, Any]]:
    attempted_at = now_iso()
    cache_entry = cache_entry or {}
    cooldown_until = cache_entry.get("cooldown_until")
    if cooldown_until and datetime.fromisoformat(cooldown_until.replace("Z", "+00:00")) > datetime.now(UTC):
        health = SourceHealth(
            id=source["id"], source=source["source"], url=source["url"], status="cooldown",
            last_attempt=attempted_at, last_success=cache_entry.get("last_success"),
            error=cache_entry.get("last_error") or "Cooldown active", offers_found=0,
            cooldown_until=cooldown_until,
        )
        return SourceResult(health=health), cache_entry
    headers = {
        "User-Agent": "LaptopDealTracker/0.1 (+personal low-frequency price research)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-GB,en;q=0.8,de;q=0.6",
    }
    if cache_entry.get("etag"):
        headers["If-None-Match"] = cache_entry["etag"]
    if cache_entry.get("last_modified"):
        headers["If-Modified-Since"] = cache_entry["last_modified"]
    request = Request(source["url"], headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            html = response.read(3_000_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            response_headers = response.headers
        if source.get("requires_saved_configuration"):
            health = SourceHealth(
                id=source["id"], source=source["source"], url=source["url"], status="configuration_required",
                last_attempt=attempted_at, last_success=attempted_at, offers_found=0,
                error="A saved exact configuration is required before this starting price can be compared.",
            )
            return SourceResult(health=health), {**cache_entry, "last_success": attempted_at, "last_error": None}
        match_status, match_details = _configuration_match(html, source) if source.get("type") != "catalog" else ("unverified", [])
        if match_status in {"mismatched", "unidentified"}:
            status = "configuration_changed" if match_status == "mismatched" else "configuration_unidentified"
            message = f"Expected configuration not confirmed: {', '.join(match_details)}"
            health = SourceHealth(
                id=source["id"], source=source["source"], url=source["url"], status=status,
                last_attempt=attempted_at, last_success=cache_entry.get("last_success"), error=message, offers_found=0,
            )
            updated_cache = {**cache_entry, "last_error": message, "configuration_match": match_status}
            return SourceResult(health=health), updated_cache
        products = _products(html)
        if source.get("type") == "catalog" and source.get("source") == "bestware":
            products = _bestware_catalog_products(html, source["url"])
        offers: list[Offer] = []
        discovered: list[dict[str, Any]] = []
        for product in products:
            title = str(product.get("name") or "")
            if source.get("keywords") and not any(keyword.lower() in title.lower() for keyword in source["keywords"]):
                continue
            laptop = None
            laptop_id = source.get("laptop_id")
            if source.get("type") == "catalog":
                laptop = _infer_laptop(product, source)
                laptop_id = laptop["id"]
                discovered.append(laptop)
            if not laptop_id:
                continue
            offer_data = _offer_block(product)
            price = number(offer_data.get("price") or offer_data.get("lowPrice"))
            shipping = number(source.get("shipping", 0))
            total = round(price + (shipping or 0), 2) if price is not None else None
            product_url = offer_data.get("url") or product.get("url") or source["url"]
            offers.append(Offer(
                id=stable_id(source["source"], str(product_url), str(laptop_id)),
                source=source["source"], seller=source["seller"], laptop_id=str(laptop_id),
                url=str(product_url), source_id=source["id"], country=source.get("country", "DE"), condition=source.get("condition", "new"),
                price=price, shipping=shipping, total_price=total,
                currency=str(offer_data.get("priceCurrency") or "EUR"),
                os_status=str((source.get("expected_fingerprint") or {}).get("os_status") or "unknown"),
                ram_gb=(source.get("expected_fingerprint") or {}).get("ram_gb"),
                ssd_gb=(source.get("expected_fingerprint") or {}).get("ssd_gb"),
                configuration_match=match_status,
                availability=_availability(offer_data.get("availability")), confidence="high" if price is not None and match_status == "matched" else "medium" if price is not None else "low",
                last_checked=attempted_at, raw_title=title,
                notes="Starting/configurator price may differ from the preferred final configuration." if source["source"] in {"bestware", "tuxedo"} else None,
            ))
        health = SourceHealth(
            id=source["id"], source=source["source"], url=source["url"], status="ok",
            last_attempt=attempted_at, last_success=attempted_at, offers_found=len(offers),
        )
        updated_cache = {
            "etag": response_headers.get("ETag"),
            "last_modified": response_headers.get("Last-Modified"),
            "offers": [offer.to_dict() for offer in offers],
            "discovered_laptops": discovered,
            "last_success": attempted_at,
            "cooldown_until": None,
            "last_error": None,
        }
        time.sleep(0.5)
        return SourceResult(offers=offers, discovered_laptops=discovered, health=health), updated_cache
    except HTTPError as error:
        if error.code == 304:
            offers = [Offer(**offer) for offer in cache_entry.get("offers", [])]
            for offer in offers:
                offer.last_checked = attempted_at
            health = SourceHealth(
                id=source["id"], source=source["source"], url=source["url"], status="not_modified",
                last_attempt=attempted_at, last_success=cache_entry.get("last_success"), offers_found=len(offers),
            )
            return SourceResult(offers=offers, discovered_laptops=cache_entry.get("discovered_laptops", []), health=health), cache_entry
        cooldown = None
        status = "failed"
        if error.code in {403, 429, 503}:
            status = "cooldown"
            hours = 24 if error.code in {403, 429} else 6
            cooldown = (datetime.now(UTC) + timedelta(hours=hours)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        message = f"HTTP {error.code}; retries paused" if cooldown else f"HTTP {error.code}"
    except (URLError, TimeoutError) as error:
        status, cooldown, message = "failed", None, f"Network error: {getattr(error, 'reason', str(error))}"
    except Exception as error:  # one adapter must never stop the full run
        status, cooldown, message = "failed", None, f"Parsing error: {type(error).__name__}"
    health = SourceHealth(
        id=source["id"], source=source["source"], url=source["url"], status=status,
        last_attempt=attempted_at, last_success=cache_entry.get("last_success"), error=message,
        offers_found=0, cooldown_until=cooldown,
    )
    updated_cache = {**cache_entry, "cooldown_until": cooldown, "last_error": message}
    return SourceResult(health=health), updated_cache
