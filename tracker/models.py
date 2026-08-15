from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Offer:
    id: str
    source: str
    seller: str
    laptop_id: str
    url: str
    source_id: str | None = None
    country: str = "DE"
    condition: str = "new"
    price: float | None = None
    shipping: float | None = 0.0
    total_price: float | None = None
    currency: str = "EUR"
    original_price: float | None = None
    os_status: str = "unknown"
    ram_gb: int | None = None
    ssd_gb: int | None = None
    configuration_match: str = "unverified"
    price_breakdown: dict[str, Any] | None = None
    effective_price: float | None = None
    value_score: int | None = None
    value_rating: str = "UNRATED"
    availability: str = "unknown"
    confidence: str = "medium"
    first_seen: str | None = None
    last_seen: str | None = None
    last_checked: str | None = None
    missed_checks: int = 0
    raw_title: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SourceHealth:
    id: str
    source: str
    url: str
    status: str
    last_attempt: str
    last_success: str | None = None
    error: str | None = None
    offers_found: int = 0
    cooldown_until: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SourceResult:
    offers: list[Offer] = field(default_factory=list)
    discovered_laptops: list[dict[str, Any]] = field(default_factory=list)
    health: SourceHealth | None = None
