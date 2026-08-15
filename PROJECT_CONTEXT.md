# Project Context

## Product decision

Laptop Deal Tracker is a temporary buying instrument, not a permanent shopping platform. Optimize changes for reaching a confident laptop purchase within months. Reject infrastructure or abstractions whose likely payback occurs after that window.

The website is the viewing layer. Python and the append-only data snapshot are the system of record. The dashboard must remain useful when a source fails and must never describe historical benchmark prices as live offers.

## Decision hierarchy

1. Do not miss a genuinely strong deal among the supported sources.
2. Make BUY / WAIT / SKIP reasoning understandable at a glance on a phone.
3. Preserve observations and unavailable listings.
4. Avoid account risk, aggressive requests, paid services, and recurring maintenance.
5. Prefer adding a fixed URL over building a fragile broad scraper.

The primary question is: **Does buying this exact laptop configuration at its ready-to-use price make more sense than continuing to wait for the XMG CORE 16 or another materially better alternative?**

## Non-negotiable behavior

- Everything in the project is written in English.
- Laptop Score is hardware-only; Value Score is price-dependent. Never blend them.
- Effective price includes shipping plus the configured Windows, RAM, and SSD allowances.
- Unknown specifications remain `null`; they are not inferred from a family name.
- A low-confidence or critically incomplete offer cannot receive BUY.
- Variant identity prefers manufacturer + model + SKU.
- Configurable targets and changing fixed prebuild pages remain separate even when they share a family SKU.
- A source fingerprint change invalidates attachment to the old exact record.
- Source failures are isolated and preserve the last valid data.
- HTTP 403 and 429 responses produce cooldown, not rapid retries.
- Personal retailer accounts are never automated.
- Data updates remain independent of frontend deployments.
- The baseline remains usable without external credentials.

## Current source boundary

V1 includes structured public-page support for Bestware/XMG, TUXEDO, supported manufacturer catalog entries, and fixed manual URLs. Discovery is deliberately limited to those supported catalogs. Expand coverage only when a concrete missing retailer or model is affecting the purchase decision.

## End state

After a laptop purchase, record the result and run the completion workflow. The final state is a read-only dashboard with the purchase banner and preserved research; scheduled tracking is disabled. Further platform development is out of scope unless the tool is deliberately repurposed for another purchase.
