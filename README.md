# Laptop Deal Tracker

Laptop Deal Tracker is a temporary, personal buying dashboard for finding a laptop in Germany. It keeps known candidates, current offers, price changes, source health, and a rule-based BUY / WAIT / SKIP recommendation in one mobile-friendly page.

The project completed its purpose on 2026-08-17 and is now a read-only purchase archive. The final choice was an XMG CORE 16 (M25) with Ryzen AI 7 350, RTX 5060, 32 GB RAM, 2 TB SSD, US International keyboard, and Windows 11 Home for EUR 1,865.69 including VAT.

The complete configuration and discount record is stored in `config/purchase.json`: EUR 532.21 total savings, or approximately 22.2% compared with the original checkout total including shipping. The public archive deliberately excludes the order number and coupon codes. Scheduled tracking is disabled; the final dashboard and price history remain available for reference.

## What it does

- Tracks fixed laptop pages without logging into shopping accounts.
- Performs limited discovery on supported public manufacturer catalogs.
- Groups several seller offers under one laptop variant.
- Preserves price and availability changes in monthly JSONL files.
- Keeps a price-independent **Laptop Score** and a separate price-dependent **Value Score**.
- Includes Windows, shipping, and required RAM/SSD allowances in the ready-to-use effective price.
- Protects fixed records with CPU/GPU/RAM/storage/OS fingerprints when retailer pages change.
- Keeps the last valid data when one source fails.
- Publishes tracking data without rebuilding the website.
- Stops scheduled tracking and displays an archive banner after the purchase is recorded.

Historical prices supplied in `config/laptops.json` are reference points only. They are never presented as current offers.

The reconciled master catalog contains 51 exact or research-stage records: the 47-row research set, derived current fixed variants, and later exact additions. The row-by-row result and post-research additions are in `config/reconciliation_2026-08-15.json`. Automatic catalog discoveries are stored separately and do not overwrite an exact configuration unless its identity and expected fingerprint match.

The earlier 20-model shortlist is audited in `config/reconciliation_previous_shortlist_2026-08-15.json`. Every line is represented. Previously unresolved Legion references were resolved to exact SKUs `83LU0057MH` and `83KYCTO1WWNL2`; the GIGABYTE `DXHG4DECC4SH` record was completed; and PCSpecialist Defiance remains an explicit configurable target because it has no stable SKU. `config/identity_migrations.json` prevents the retired placeholder identities from returning through old generated data.

The Laptops area opens in a concise **Models** view using explicit, reviewed family assignments from `config/families.json`. Expand a multi-variant model to see every exact SKU, or switch to **Variants** for the complete flat catalog. Filters apply before grouping, and desktop headers or the mobile sort controls can sort in either direction. Laptop Score descending is the default.

To resume the project in another task or on another computer, start with [`CONTEXT.md`](CONTEXT.md). To submit a retailer link or screenshots for a new laptop, use [`CANDIDATE_INTAKE.md`](CANDIDATE_INTAKE.md); the same full submission prompt can be copied from the dashboard's Preferences area.

## Architecture

```text
GitHub Actions                 GitHub Pages
      │                              │
      ├─ Python tracker              └─ static mobile dashboard
      ├─ source adapters                         │
      ├─ scoring                                fetches
      └─ commits public data                     │
                 │                               │
                 └──────── data branch ──────────┘
```

The `main` branch contains code and the static site. The `data` branch contains `public-data/dashboard.json`, current normalized records, monthly history, cache metadata, and concise run logs. A normal tracking run changes only the `data` branch, so it does not trigger a Pages deployment.

Expected monthly cost is €0 for a public repository using standard GitHub-hosted runners and GitHub Pages. Do not add a payment method or paid services for this project unless you intentionally change that assumption.

## Local use

Python 3.11 or newer is the only requirement.

```powershell
python -m unittest discover -s tests -v
python -m tracker --offline --output build-data
python -m http.server 8000
```

Then open `http://localhost:8000/site/`. Offline mode creates a dashboard from the seeded catalog without contacting stores.

To perform a live check:

```powershell
python -m tracker --mode all --output build-data
```

Live checks are intentionally low frequency. A source may return zero offers when its public page does not expose usable structured product data; this is reported as source health rather than guessed.

## GitHub setup

1. Create a public GitHub repository and push this project to its `main` branch.
2. In **Settings → Pages**, select **GitHub Actions** as the source.
3. Open **Actions → Update laptop data → Run workflow** and choose `all`. The first run creates the `data` branch.
4. Open **Actions → Deploy dashboard → Run workflow**. Later site-code pushes deploy automatically.
5. Use the Pages URL immediately. Add `laptops.dazu.xyz` later in the Pages custom-domain settings if desired.

No baseline source needs credentials. The workflows use only GitHub's temporary repository token. Never commit API keys, shopping credentials, or Telegram tokens.

Scheduled watchlist checks run at 05:17, 11:17, 17:17, and 23:17 UTC. Discovery runs at 06:43 and 18:43 UTC. GitHub may delay scheduled jobs during heavy demand. Public scheduled workflows can be disabled after prolonged repository inactivity; use the manual workflow button to re-enable or verify them.

## Adding a fixed offer URL

Edit `config/manual_offers.json` and copy the disabled example:

```json
{
  "id": "retailer-aero-x16",
  "enabled": true,
  "source": "retailer-name",
  "seller": "Retailer name",
  "laptop_id": "gigabyte-aero-x16-1wh93dec64ah",
  "url": "https://retailer.example/product-page",
  "country": "DE",
  "condition": "new"
}
```

The generic adapter reads public JSON-LD Product data when the page provides it. If the page is blocked, requires JavaScript, or lacks a reliable price, the adapter reports the problem and keeps the previous valid observation. It does not bypass protection.

Add a new variant to `config/laptops.json` before attaching a fixed URL. Use a manufacturer + model + SKU identity whenever possible. Use `null` for unknown specifications.

## Adding a laptop you find

Send the product link, screenshots, or both in a Codex task with this repository. The candidate intake process extracts listing evidence, researches missing specifications from reliable sources, checks SKU aliases and the full configuration fingerprint for duplicates, and then either updates the existing record or creates a genuinely distinct exact configuration. It calculates component indices, criterion scores, Laptop Score, effective price, Value Score, and recommendation before publishing.

Screenshots and unavailable listings are preserved as dated evidence rather than live offers. The final identity check is reviewed deliberately: a marketplace title or family name alone is not allowed to create a record or attach a price. See [`CANDIDATE_INTAKE.md`](CANDIDATE_INTAKE.md) for the checklist and reusable request.

## Scores, effective prices, and decisions

`config/preferences.yaml` is JSON-compatible YAML so the tracker stays dependency-free. Laptop Score uses the ten visible criteria with fixed weights: GPU 22, CPU 16, memory/storage 12, cooling/build 12, keyboard 12, display 10, battery/charging 7, portability 5, Windows Hello 3, and miscellaneous 1. It is rounded half-up and never changes with price.

Value Score uses the current effective price: listing + shipping + required allowances. Defaults are €50 for Windows, €90 for a 32 GB RAM upgrade, and €70 for a 1 TB SSD upgrade. The dashboard's Preferences area can change these allowances on one device without modifying the public data or Laptop Score.

CPU and GPU comparison entries live in `config/components.json`. Their 0–100 indices are personal comparison aids with dates, confidence, and evidence; they are not universal benchmark percentages.

The Preferences area also contains a compact copyable version of the ideal-laptop requirements. The complete reusable brief is stored in `config/ideal_requirements.json`.

The Prices area includes dated marketplace research from `config/market_leads.json`. Used/refurbished leads are deliberately not treated as live scored offers until the exact configuration and current seller terms are rechecked. Configuration conflicts are displayed as rejected leads. This prevents a marketplace title from bypassing the normal identity safeguards.

A high score alone cannot produce BUY NOW. The exact offer must be matched with high confidence, have an effective price, meet the Laptop and Value thresholds, and permit required upgrades. Changed, unidentified, or unresolved configurations remain UNRATED rather than inheriting another variant's price.

## Purchase completion

The purchase-completion workflow was run on 2026-08-17. It:

1. records the final purchase;
2. creates one final offline snapshot using the last valid prices;
3. publishes the archive banner;
4. disables the scheduled tracker workflow.

The static dashboard and its history remain readable. The repository may be downloaded or archived, while the default GitHub Pages URL can remain online at no monthly cost.

## Limits by design

- This is a decision aid, not a price guarantee. Always verify the exact SKU, keyboard, shipping, VAT, returns, warranty, and final configured price before buying.
- Configurator starting prices may not represent the desired 32 GB / 1 TB configuration and are labeled accordingly.
- The baseline does not use eBay's production Browse API because access requires a separate approval process.
- Retailer coverage is intentionally selective. Add a source only when it materially improves the buying decision.
- There is no account system, cloud preference synchronization, Telegram integration, paid AI, or server database.
