# Laptop Deal Tracker — Continuation Context

Use this file to continue the project in a new Codex task, on another computer, or after a long pause. Give the new task this repository and say: **Read `CONTEXT.md`, then inspect the current repository and live dashboard before making changes.**

## Purpose and lifespan

Laptop Deal Tracker is a temporary English-only buying tool for finding one laptop in Germany over the next few months. It is not a permanent shopping platform. The target cost is EUR 0/month. After the purchase, record the result, take one final snapshot, disable scheduled checks, and keep the dashboard as a read-only archive.

Repository: <https://github.com/danielmza-web/laptop-deal-tracker>

Live dashboard: <https://danielmza-web.github.io/laptop-deal-tracker/>

## Current product state

- The static mobile/desktop dashboard is hosted by GitHub Pages.
- Python tracking runs in GitHub Actions; normal data updates are written to the `data` branch without rebuilding the frontend.
- The master catalog currently has 51 exact or research-stage records: the reconciled 47-row research set plus current fixed variants and later exact Lenovo and ASUS additions.
- Laptops defaults to explicit family grouping with a remembered Models/Variants toggle. Grouping is presentation-only and never merges records, offers, fingerprints, or history.
- Three user-found Galaxus listings were reconciled on 2026-08-15: existing Intel SKU `83F3003HPB` was updated, while English-keyboard AMD SKUs `83LT000MUS` and `83LT001WPB` were added separately.
- Laptop Score is hardware-only. Value Score is price-dependent and uses ready-to-use cost. They are never combined.
- The dashboard has Overview, Laptops, Prices, Sources, and Preferences. Shortlist, Watchlist, Discovered, and Archived are filters in Laptops.
- Preferences contains the complete ideal-laptop brief, a one-click copy button, local cost allowances, and a copyable new-candidate submission template.

## User and ideal laptop

The buyer needs a durable approximately 16-inch laptop for programming, computer vision, local AI/CUDA work, occasional CAD, productivity, external displays, and gaming. The detailed authoritative brief is `config/ideal_requirements.json`; the compact version appears in the Preferences view.

Core target:

- modern strong CPU with good sustained performance and preferably better efficiency than older HX designs;
- RTX 5060/5070-class or better, evaluated by VRAM, real TGP, cooling, and sustained output;
- 32 GB dual-channel RAM and 1 TB replaceable NVMe storage, ideally two SO-DIMM and two M.2 slots;
- 16:10 2560x1600-class good-gamut display at 120-165 Hz or faster, preferably matte/anti-glare;
- English/international QWERTY with numpad; German QWERTZ only for a meaningful advantage;
- durable, serviceable chassis, useful quiet mode, 70 Wh+ battery, USB-C PD, and ideally near 2.2 kg or less;
- Windows Hello is useful but not essential;
- target effective price EUR 1,400-1,800, about EUR 2,000 only for a clearly low-compromise model.

Used/refurbished can be considered only with a meaningful discount and checks for exact SKU, battery/SSD health, display, keyboard, hinges, ports, fans, charger, locks, invoice, seller, warranty, and returns.

## Scoring and prices

Laptop Score uses visible criterion scores and half-up rounding:

- GPU 22
- CPU 16
- memory/storage 12
- cooling/build 12
- keyboard 12
- display 10
- battery/charging 7
- portability 5
- Windows Hello 3
- miscellaneous/ports 1

Default Value Score allowances are EUR 50 Windows, EUR 90 RAM, and EUR 70 SSD. Effective price equals listing + shipping + required allowances. Device-local overrides change Value Score only.

BUY NOW requires Value Score at least 90, Laptop Score at least 75, exact high-confidence identity, and feasible upgrades. Uncertainty downgrades or blocks the recommendation. Historical prices and screenshots never masquerade as live offers.

## Identity and duplicate safeguards

Before adding any laptop, match manufacturer SKU and aliases. Then compare the configuration fingerprint: CPU, GPU, real TGP, RAM, SSD, keyboard, OS status, and configuration type.

- Exact match: update the existing record or add a seller/price observation.
- Same family but different fingerprint: create a separate exact configuration.
- Conflicting or unresolved identity: archive/unrate it; do not guess.
- A retailer changing a CPU or GPU behind the same URL produces `configuration_changed` and cannot contaminate the old record.
- Unknown specifications remain `null` and display as **Unknown**.

The complete intake procedure and reusable prompt are in `CANDIDATE_INTAKE.md`.

## Important files

- `config/laptops.json` — exact master configurations, scores, evidence, targets, snapshots, and fingerprints
- `config/components.json` — reusable CPU and GPU comparison indices
- `config/manual_offers.json` — exact fixed retailer URLs with expected SKU/fingerprint protection
- `config/sources.json` — supported automatic sources and catalogs
- `config/ideal_requirements.json` — complete reusable buying brief
- `config/market_leads.json` — dated used/refurbished/marketplace research
- `config/reconciliation_2026-08-15.json` — row-level research reconciliation and later additions
- `tracker/` — fetching, normalization, safety, history, and scoring
- `site/` — framework-free responsive dashboard
- `.github/workflows/` — scheduled data checks, Pages deployment, and purchase completion
- `README.md` — operations and setup
- `PROJECT_CONTEXT.md` — stable product rules

## Adding a candidate

The normal user flow is intentionally simple: send a link and/or screenshots in a Codex task. The maintainer extracts listing facts, searches reliable sources for missing information, checks duplicates, adds or updates the exact record, calculates component/criterion/Laptop/Value scores, adds a protected fixed URL when suitable, regenerates data, tests, and publishes.

Do not build blind automatic database insertion from marketplace titles. Automatic page extraction is useful for evidence and live prices, but reviewed identity is required before a record or offer is attached.

## Verification before publishing

Run:

```powershell
python -m unittest discover -s tests -v
python -m tracker --offline --output build-data
python scripts/validate_data.py build-data
```

Also check `git diff --check`, inspect generated counts and the relevant records, and test the dashboard on desktop and mobile when UI changes. After pushing `main`, confirm the Pages deployment and manually run the `Update laptop data` workflow in `all` mode when catalog or source configuration changed.

## Automation and shutdown

Watchlist checks run four times daily; discovery runs twice daily. Source failures are independent and retain last-known valid data. No baseline credentials or paid API are required.

After purchase, run **Complete purchase and stop tracking** in GitHub Actions with the chosen laptop, final EUR price, and date. It records the purchase, publishes the final archive snapshot/banner, and disables scheduled tracking. Keep or download the repository and optionally remove any custom domain while retaining the default Pages URL.
