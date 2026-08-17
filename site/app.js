const state = {
  data: null,
  view: "overview",
  filters: { price: "", gpu: "", brand: "", status: "", numpad: false },
  sort: "laptop",
  sortDirection: "desc",
  catalogMode: localStorage.getItem("laptop-tracker-catalog-mode") || "models",
  expandedFamilies: new Set(),
  preferences: JSON.parse(localStorage.getItem("laptop-tracker-preferences") || "{}"),
};

const views = {
  overview: ["Decision desk", "Overview", "Best current value and best hardware fit remain separate."],
  laptops: ["Complete catalog", "Laptops", "Sort and filter every exact, discovered, and archived configuration."],
  prices: ["Observed prices", "Prices", "Live observations, dated research snapshots, and effective ready-to-use costs."],
  sources: ["Tracking health", "Sources", "Configuration changes are isolated before they can contaminate an exact laptop."],
  preferences: ["On this device", "Preferences", "Adjust cost allowances locally without changing the public project data."],
};

const CRITERIA = [
  ["gpu", "GPU / VRAM / TGP", 22], ["cpu", "CPU performance / efficiency", 16],
  ["memory_storage", "RAM / SSD / expandability", 12], ["cooling_build", "Cooling / sustained / build", 12],
  ["keyboard", "Keyboard / numpad", 12], ["display", "Display", 10],
  ["battery_usb_c", "Battery / USB-C", 7], ["portability", "Portability / charger", 5],
  ["windows_hello", "Windows Hello", 3], ["ports_misc", "Ports / miscellaneous", 1],
];

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[character]));
const display = value => value === null || value === undefined || value === "" ? "Unknown" : value;
const money = value => value == null ? "Unknown" : new Intl.NumberFormat("en-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(value);
const scoreText = value => value == null ? "—" : String(Math.round(value));
const confidenceRank = value => ({ low: 1, medium: 2, high: 3, verified: 4 }[value] || 1);

function allowances() {
  const base = state.data?.preferences?.cost_allowances || { windows: 50, ram_32gb: 90, ssd_1tb: 70 };
  return {
    windows: Number(state.preferences.windowsCost ?? base.windows),
    ram_32gb: Number(state.preferences.ramCost ?? base.ram_32gb),
    ssd_1tb: Number(state.preferences.ssdCost ?? base.ssd_1tb),
  };
}

function priceBreakdown(laptop, offer) {
  const listing = offer.price ?? offer.total_price;
  if (listing == null) return null;
  const costs = allowances();
  const shipping = Number(offer.price == null ? 0 : offer.shipping || 0);
  const osStatus = offer.os_status || laptop.os_status || "unknown";
  const windows = osStatus === "windows_included" ? 0 : costs.windows;
  const ram = offer.ram_gb ?? laptop.ram_gb;
  const storage = offer.ssd_gb ?? laptop.ssd_gb;
  let ramCost = 0, ssdCost = 0, feasible = true;
  const blockers = [];
  if (ram == null) blockers.push("RAM capacity is unknown");
  else if (ram < 32) {
    if (laptop.ram_upgradeable === true) ramCost = costs.ram_32gb;
    else { feasible = false; blockers.push("RAM cannot reach 32 GB"); }
  }
  if (storage == null) blockers.push("Storage capacity is unknown");
  else if (storage < 1000) {
    if (laptop.ssd_upgradeable !== false) ssdCost = costs.ssd_1tb;
    else { feasible = false; blockers.push("Storage cannot reach 1 TB"); }
  }
  return {
    listing_price: Number(listing), shipping, windows, ram: ramCost, ssd: ssdCost,
    effective_price: Number(listing) + shipping + windows + ramCost + ssdCost,
    os_status: osStatus, upgrade_feasible: feasible, blockers,
  };
}

function targetPrices(laptop, condition = "new") {
  const score = laptop.laptop_score;
  if (score == null) return null;
  const configured = laptop.target_prices || {};
  const consider = Number(configured.consider ?? Math.max(1200, Math.min(2300, 1800 * score / 85)));
  const strong = Number(configured.strong ?? consider * .9);
  const buy = Number(configured.buy_now ?? consider * .82);
  const factor = { new: 1, open_box: .9, refurbished: .8, used: .65 }[condition] || 1;
  return { buy: buy * factor, strong: strong * factor, consider: consider * factor };
}

function interpolate(value, x1, x2, y1, y2) {
  const ratio = x2 <= x1 ? 1 : Math.max(0, Math.min(1, (value - x1) / (x2 - x1)));
  return y1 + (y2 - y1) * ratio;
}

function calculateValue(laptop, offer, breakdown) {
  if (!breakdown || laptop.laptop_score == null || ["mismatched", "unidentified"].includes(offer.configuration_match)) return null;
  const target = targetPrices(laptop, offer.condition);
  const price = breakdown.effective_price;
  let value;
  if (price <= target.buy) value = 95 + Math.min(5, Math.max(0, (target.buy - price) / target.buy * 25));
  else if (price <= target.strong) value = interpolate(price, target.buy, target.strong, 95, 90);
  else if (price <= target.consider) value = interpolate(price, target.strong, target.consider, 90, 80);
  else if (price <= target.consider * 1.25) value = interpolate(price, target.consider, target.consider * 1.25, 80, 50);
  else value = interpolate(price, target.consider * 1.25, target.consider * 1.75, 50, 0);
  const evidence = Math.min(confidenceRank(laptop.confidence), confidenceRank(offer.confidence));
  if (evidence === 2) value -= 3;
  if (evidence === 1) value -= 8;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function recommendation(laptop, offer, value, breakdown) {
  if (!offer || value == null) return ["UNRATED", "No current price is attached to a reliably identified configuration."];
  if (!breakdown.upgrade_feasible) return ["SKIP", "The configuration cannot reach the minimum RAM or storage requirement."];
  if (value >= 90 && laptop.laptop_score >= 75) {
    const criticalKnown = [laptop.cpu, laptop.gpu, offer.ram_gb ?? laptop.ram_gb, offer.ssd_gb ?? laptop.ssd_gb].every(value => value != null);
    const verified = confidenceRank(laptop.confidence) >= 3 && confidenceRank(offer.confidence) >= 3 && offer.configuration_match === "matched" && criticalKnown;
    return verified ? ["BUY NOW", "Excellent effective price with a verified exact configuration."] : ["STRONGLY CONSIDER", "Excellent price, but verify the remaining assumptions before buying."];
  }
  if (value >= 82) return ["STRONGLY CONSIDER", "Strong value after Windows and required upgrades are included."];
  if (value >= 70) return ["WAIT", "The effective price is not compelling enough yet."];
  return ["SKIP", "The effective price does not compensate for the compromises."];
}

function decorate(laptop) {
  const offers = (laptop.offers || []).map(offer => {
    const breakdown = priceBreakdown(laptop, offer);
    const value = calculateValue(laptop, offer, breakdown);
    return { ...offer, price_breakdown: breakdown, effective_price: breakdown?.effective_price ?? null, value_score: value };
  });
  const available = offers.filter(offer => offer.effective_price != null && !["out_of_stock", "listing_removed"].includes(offer.availability) && !["mismatched", "unidentified"].includes(offer.configuration_match));
  available.sort((a, b) => (b.value_score ?? -1) - (a.value_score ?? -1) || a.effective_price - b.effective_price);
  const best = available[0] || null;
  const value = best?.value_score ?? null;
  const [decision, reason] = recommendation(laptop, best, value, best?.price_breakdown);
  return { ...laptop, offers, best_offer: best, value_score: value, decision, decision_reason: reason };
}

function allLaptops() { return (state.data?.laptops || []).map(decorate); }

function naturalDirection(key) { return ["price", "model", "os"].includes(key) ? "asc" : "desc"; }
function laptopSortValue(item, key) {
  if (key === "model") return `${item.brand || ""} ${item.model || ""}`.toLowerCase();
  if (key === "os") return osLabel(item.best_offer?.price_breakdown?.os_status || item.os_status).toLowerCase();
  if (key === "decision") return ({ "BUY NOW": 5, "STRONGLY CONSIDER": 4, WAIT: 3, SKIP: 2, UNRATED: 1 })[item.decision] ?? null;
  if (key === "price") return item.best_offer?.effective_price ?? null;
  if (key === "laptop") return item.laptop_score ?? null;
  if (key === "value") return item.value_score ?? null;
  return item.criteria_scores?.[key] ?? null;
}
function compareValues(a, b, direction = state.sortDirection) {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  const result = typeof a === "string" ? a.localeCompare(b) : a - b;
  return direction === "asc" ? result : -result;
}
function sortedLaptops(items = allLaptops()) {
  return [...items].sort((a, b) => compareValues(laptopSortValue(a, state.sort), laptopSortValue(b, state.sort)) || compareValues(a.laptop_score, b.laptop_score, "desc") || a.id.localeCompare(b.id));
}

function filtered(items) {
  return items.filter(laptop => {
    if (state.filters.price && (laptop.best_offer?.effective_price == null || laptop.best_offer.effective_price > Number(state.filters.price))) return false;
    if (state.filters.gpu && laptop.gpu !== state.filters.gpu) return false;
    if (state.filters.brand && laptop.brand !== state.filters.brand) return false;
    if (state.filters.status && laptop.status !== state.filters.status) return false;
    if (state.filters.numpad && laptop.numpad !== true) return false;
    return true;
  });
}

async function loadData(force = false) {
  const status = $("#data-status");
  status.textContent = "Loading data…";
  const base = window.LAPTOP_TRACKER_CONFIG?.dataUrl || "../build-data/dashboard.json";
  const separator = base.includes("?") ? "&" : "?";
  try {
    const response = await fetch(`${base}${separator}v=${force ? Date.now() : "current"}`, { cache: force ? "reload" : "default" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    localStorage.setItem("laptop-tracker-last-data", JSON.stringify(state.data));
    renderAll();
    status.textContent = `Updated ${formatDate(state.data.generated_at)}`;
  } catch (error) {
    const cached = localStorage.getItem("laptop-tracker-last-data");
    if (cached) {
      state.data = JSON.parse(cached); renderAll(); status.textContent = "Showing saved snapshot";
    } else {
      $("#view-content").innerHTML = emptyState("Data unavailable", "Run the tracker once or check the configured data URL.", "!");
      status.textContent = "Data unavailable";
    }
  }
}

function formatDate(value) {
  if (!value) return "never";
  return new Intl.DateTimeFormat("en-DE", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function renderAll() {
  if (!state.data) return;
  renderSummary(); renderFilters(); renderView();
  const purchase = state.data.purchase_completed;
  const banner = $("#purchase-banner");
  if (purchase) {
    banner.classList.remove("hidden");
    const configuration = purchase.configuration_summary
      ? `<span>${escapeHtml(purchase.configuration_summary)}</span>`
      : "";
    const savings = purchase.pricing?.total_savings != null
      ? `<span>Saved ${money(purchase.pricing.total_savings)} (${escapeHtml(String(purchase.pricing.effective_discount_percent))}%). Tracking is archived.</span>`
      : `<span>Tracking is archived.</span>`;
    banner.innerHTML = `<strong>Purchase completed: ${escapeHtml(purchase.laptop)} · ${money(purchase.price)} · ${escapeHtml(purchase.date)}</strong>${configuration}${savings}`;
  } else banner.classList.add("hidden");
}

function renderSummary() {
  const summary = state.data.summary;
  $("#major-deals").textContent = summary.major_deals;
  $("#price-drops").textContent = summary.price_drops_24h;
  $("#new-models").textContent = summary.new_models_24h;
  $("#active-offers").textContent = summary.active_offers;
  const laptops = allLaptops();
  const best = [...laptops].filter(item => item.value_score != null && item.decision !== "SKIP").sort((a, b) => b.value_score - a.value_score || b.laptop_score - a.laptop_score)[0]
    || [...laptops].filter(item => item.value_score != null).sort((a, b) => b.value_score - a.value_score || b.laptop_score - a.laptop_score)[0]
    || [...laptops].filter(item => item.laptop_score != null).sort((a, b) => b.laptop_score - a.laptop_score)[0];
  if (!best) return;
  $("#best-title").textContent = `${best.brand} ${best.model}`;
  $("#best-summary").textContent = best.best_offer ? `${best.decision}: ${best.decision_reason}` : "Highest hardware fit; waiting for a reliably identified live price.";
  $("#best-laptop-score").textContent = scoreText(best.laptop_score);
  $("#best-value-score").textContent = scoreText(best.value_score);
  const actions = [];
  if (best.best_offer?.url) actions.push(`<a class="primary-button" href="${escapeHtml(best.best_offer.url)}" target="_blank" rel="noopener">Open offer ↗</a>`);
  actions.push(`<button class="secondary-button" type="button" data-details="${escapeHtml(best.id)}">Review scores</button>`);
  $("#best-actions").innerHTML = actions.join("");
}

function renderFilters() {
  const laptops = state.data.laptops;
  const gpu = $("#filter-gpu"), brand = $("#filter-brand");
  const currentGpu = state.filters.gpu, currentBrand = state.filters.brand;
  gpu.innerHTML = `<option value="">All GPUs</option>${[...new Set(laptops.map(item => item.gpu).filter(Boolean))].sort().map(value => `<option>${escapeHtml(value)}</option>`).join("")}`;
  brand.innerHTML = `<option value="">All brands</option>${[...new Set(laptops.map(item => item.brand).filter(Boolean))].sort().map(value => `<option>${escapeHtml(value)}</option>`).join("")}`;
  gpu.value = currentGpu; brand.value = currentBrand;
  $("#filter-status").value = state.filters.status;
  $("#sort-by").value = state.sort;
  $("#sort-direction").textContent = state.sortDirection === "asc" ? "↑ Ascending" : "↓ Descending";
  $("#sort-direction").setAttribute("aria-label", `Sort ${state.sortDirection === "asc" ? "ascending" : "descending"}`);
  const count = Object.values(state.filters).filter(Boolean).length;
  $("#filter-count").textContent = count ? `(${count})` : "";
}

function renderView() {
  const [eyebrow, title, description] = views[state.view];
  $("#view-eyebrow").textContent = eyebrow; $("#view-title").textContent = title; $("#view-description").textContent = description;
  const showFilters = state.view === "laptops";
  $("#filter-toggle").classList.toggle("hidden", !showFilters);
  if (!showFilters) $("#filters").classList.add("hidden");
  if (state.view === "overview") return renderOverview();
  if (state.view === "laptops") return renderLaptopTable();
  if (state.view === "prices") return renderPrices();
  if (state.view === "sources") return renderSources();
  return renderPreferences();
}

function scorePair(laptop) {
  return `<div class="dual-scores"><div><strong>${scoreText(laptop.laptop_score)}</strong><small>Laptop</small></div><div class="value"><strong>${scoreText(laptop.value_score)}</strong><small>Value</small></div></div>`;
}

function compactCard(laptop, rank = null) {
  const offer = laptop.best_offer;
  const cpuScore = laptop.criteria_scores?.cpu;
  const gpuScore = laptop.criteria_scores?.gpu;
  const snapshot = laptop.market_snapshot;
  const price = offer ? money(offer.price ?? offer.total_price) : snapshot ? `Snapshot ${money(snapshot.price_eur)}` : "No live price";
  const effective = offer ? money(offer.effective_price) : "Unknown";
  return `<article class="opportunity-card">
    <header>${rank ? `<span class="rank">${rank}</span>` : ""}<div><h3>${escapeHtml(laptop.brand)} ${escapeHtml(laptop.model)}</h3><p>${escapeHtml(laptop.variant)}</p></div></header>
    <div class="component-line"><span>CPU <b>${escapeHtml(display(laptop.cpu))}</b><em>${scoreText(cpuScore)}/100</em></span><span>GPU <b>${escapeHtml(display(laptop.gpu))}</b><em>${scoreText(gpuScore)}/100</em></span></div>
    <div class="mini-specs"><span>${escapeHtml(display(laptop.ram_gb))} GB RAM</span><span>${laptop.ssd_gb ? `${laptop.ssd_gb / 1000} TB SSD` : "Storage Unknown"}</span><span>${escapeHtml(display(laptop.resolution))}</span><span>${laptop.weight_kg ? `${laptop.weight_kg} kg` : "Weight Unknown"}</span></div>
    <div class="offer-summary"><div><small>Listing</small><strong>${price}</strong></div><div><small>Ready-to-use</small><strong>${effective}</strong></div><span class="os-badge ${escapeHtml(offer?.price_breakdown?.os_status || laptop.os_status || "unknown")}">${escapeHtml(osLabel(offer?.price_breakdown?.os_status || laptop.os_status))}</span></div>
    <footer>${scorePair(laptop)}<div><span class="pill ${decisionClass(laptop.decision)}">${escapeHtml(laptop.decision)}</span><button class="text-button" data-details="${escapeHtml(laptop.id)}">Details</button></div></footer>
  </article>`;
}

function renderOverview() {
  const all = allLaptops();
  const value = [...all].filter(item => item.value_score != null).sort((a, b) => b.value_score - a.value_score || b.laptop_score - a.laptop_score).slice(0, 5);
  const hardware = [...all].filter(item => item.laptop_score != null).sort((a, b) => b.laptop_score - a.laptop_score).slice(0, 5);
  $("#view-content").className = "overview-sections";
  $("#view-content").innerHTML = `<section class="ranking-section"><div class="section-title"><div><span class="eyebrow">Live and adjusted</span><h3>Best value now</h3></div><p>Ranked using listing, shipping, Windows, RAM, and SSD costs.</p></div><div class="opportunity-grid">${value.length ? value.map((item, index) => compactCard(item, index + 1)).join("") : emptyState("No verified live value yet", "Hardware scores remain available while sources are checked.", "◎")}</div></section>
  <section class="ranking-section"><div class="section-title"><div><span class="eyebrow">Price independent</span><h3>Best laptops overall</h3></div><p>Hardware fit only. Expensive laptops do not receive a higher score.</p></div><div class="opportunity-grid">${hardware.map((item, index) => compactCard(item, index + 1)).join("")}</div></section>`;
}

function distinct(items, getter) { return [...new Set(items.map(getter).filter(value => value !== null && value !== undefined && value !== ""))]; }
function numericRange(items, getter, suffix = "") {
  const values = distinct(items, getter).map(Number).filter(Number.isFinite).sort((a, b) => a - b);
  if (!values.length) return "Unknown";
  return values.length === 1 ? `${values[0]}${suffix}` : `${values[0]}–${values.at(-1)}${suffix}`;
}
function textRange(items, getter, scoreGetter = null) {
  const values = distinct(items, getter);
  if (!values.length) return "Unknown";
  if (scoreGetter) values.sort((a, b) => Math.max(...items.filter(item => getter(item) === a).map(scoreGetter)) - Math.max(...items.filter(item => getter(item) === b).map(scoreGetter)));
  else values.sort((a, b) => String(a).localeCompare(String(b)));
  return values.length === 1 ? String(values[0]) : `${values[0]} → ${values.at(-1)}`;
}
function familyGroups(matches, all) {
  const totals = new Map();
  all.forEach(item => { const key = item.family_id || item.id; totals.set(key, (totals.get(key) || 0) + 1); });
  const groups = new Map();
  matches.forEach(item => {
    const key = item.family_id || item.id;
    if (!groups.has(key)) groups.set(key, { id: key, label: item.family_label || `${item.brand} ${item.model}`, items: [], total: totals.get(key) || 1 });
    groups.get(key).items.push(item);
  });
  return [...groups.values()].map(group => {
    const current = group.items.filter(item => item.best_offer?.effective_price != null);
    const decisions = ["BUY NOW", "STRONGLY CONSIDER", "WAIT", "SKIP", "UNRATED"].map(decision => [decision, group.items.filter(item => item.decision === decision).length]).filter(([, count]) => count);
    const best = getter => { const values = group.items.map(getter).filter(value => value != null); return values.length ? Math.max(...values) : null; };
    return { ...group,
      laptop_score: best(item => item.laptop_score),
      value_score: current.length ? best(item => item.value_score) : null,
      effective_price: current.length ? Math.min(...current.map(item => item.best_offer.effective_price)) : null,
      cpu_score: best(item => item.criteria_scores?.cpu), gpu_score: best(item => item.criteria_scores?.gpu),
      display_score: best(item => item.criteria_scores?.display), portability_score: best(item => item.criteria_scores?.portability),
      decisions, priced: current.length,
      os_sort: textRange(group.items, item => osLabel(item.best_offer?.price_breakdown?.os_status || item.os_status)).toLowerCase(),
      decision_score: best(item => ({ "BUY NOW": 5, "STRONGLY CONSIDER": 4, WAIT: 3, SKIP: 2, UNRATED: 1 })[item.decision]),
    };
  });
}
function groupSortValue(group, key) {
  return ({ model: group.label.toLowerCase(), laptop: group.laptop_score, value: group.value_score, price: group.effective_price, cpu: group.cpu_score, gpu: group.gpu_score, display: group.display_score, portability: group.portability_score, os: group.os_sort, decision: group.decision_score })[key] ?? null;
}
function sortedGroups(groups) { return [...groups].sort((a, b) => compareValues(groupSortValue(a, state.sort), groupSortValue(b, state.sort)) || compareValues(a.laptop_score, b.laptop_score, "desc") || a.label.localeCompare(b.label)); }
function variantRow(laptop, nested = false) {
  return `<tr class="${nested ? "variant-row" : ""}"><td><button class="row-title" data-details="${escapeHtml(laptop.id)}"><strong>${escapeHtml(laptop.brand)} ${escapeHtml(laptop.model)}</strong><small>${escapeHtml(laptop.sku || laptop.sku_aliases?.[0] || "No exact SKU")}</small></button></td><td>${escapeHtml(display(laptop.cpu))}<small>${scoreText(laptop.criteria_scores?.cpu)}/100</small></td><td>${escapeHtml(display(laptop.gpu))}<small>${scoreText(laptop.criteria_scores?.gpu)}/100</small></td><td><strong>${scoreText(laptop.laptop_score)}</strong></td><td><strong>${scoreText(laptop.value_score)}</strong></td><td>${money(laptop.best_offer?.effective_price)}</td><td>${escapeHtml(osLabel(laptop.best_offer?.price_breakdown?.os_status || laptop.os_status))}</td><td><span class="pill ${decisionClass(laptop.decision)}">${escapeHtml(laptop.decision)}</span></td></tr>`;
}
function sortHeader(label, key) {
  const active = state.sort === key, arrow = active ? (state.sortDirection === "asc" ? "↑" : "↓") : "";
  return `<th aria-sort="${active ? (state.sortDirection === "asc" ? "ascending" : "descending") : "none"}"><button class="sort-header ${active ? "active" : ""}" data-sort-key="${key}">${label}<span aria-hidden="true">${arrow}</span></button></th>`;
}
function groupSummary(group) {
  const items = group.items, prices = items.map(item => item.best_offer?.effective_price).filter(value => value != null);
  const scoreRange = numericRange(items, item => item.laptop_score);
  const decisionText = group.decisions.map(([name, count]) => `${count} ${name.toLowerCase()}`).join(" · ");
  const matchText = items.length < group.total ? `${items.length} matching of ${group.total} total` : `${group.total} variant${group.total === 1 ? "" : "s"}`;
  const details = `${numericRange(items, item => item.ram_gb, " GB RAM")} · ${numericRange(items, item => item.ssd_gb == null ? null : item.ssd_gb / 1000, " TB SSD")} · ${textRange(items, item => item.keyboard_layout)} · ${numericRange(items, item => item.weight_kg, " kg")}`;
  const button = group.total > 1 ? `data-family-toggle="${escapeHtml(group.id)}" aria-expanded="${state.expandedFamilies.has(group.id)}"` : `data-details="${escapeHtml(items[0].id)}"`;
  return `<tr class="family-row"><td><button class="row-title family-title" ${button}><strong>${escapeHtml(group.label)} <span>${group.total}</span></strong><small>${escapeHtml(matchText)} · ${escapeHtml(details)}</small></button></td><td>${escapeHtml(textRange(items, item => item.cpu, item => item.criteria_scores?.cpu ?? 0))}</td><td>${escapeHtml(textRange(items, item => item.gpu, item => item.criteria_scores?.gpu ?? 0))}</td><td><strong>${scoreRange}</strong></td><td><strong>${scoreText(group.value_score)}</strong><small>${group.priced} priced</small></td><td>${prices.length ? money(Math.min(...prices)) + (Math.min(...prices) !== Math.max(...prices) ? `–${money(Math.max(...prices))}` : "") : "Unknown"}</td><td>${escapeHtml(textRange(items, item => osLabel(item.best_offer?.price_breakdown?.os_status || item.os_status)))}</td><td><small>${escapeHtml(decisionText)}</small></td></tr>`;
}
function groupCard(group, index) {
  const items = group.items, expanded = state.expandedFamilies.has(group.id), multi = group.total > 1;
  const specs = `${textRange(items, item => item.cpu, item => item.criteria_scores?.cpu ?? 0)} · ${textRange(items, item => item.gpu, item => item.criteria_scores?.gpu ?? 0)} · ${numericRange(items, item => item.ram_gb, " GB RAM")} · Score ${numericRange(items, item => item.laptop_score)}`;
  return `<article class="family-card"><button class="family-card-button" ${multi ? `data-family-toggle="${escapeHtml(group.id)}" aria-expanded="${expanded}"` : `data-details="${escapeHtml(items[0].id)}"`}><span class="rank">${index + 1}</span><span><strong>${escapeHtml(group.label)}</strong><small>${escapeHtml(items.length < group.total ? `${items.length} matching of ${group.total} total` : `${group.total} variant${group.total === 1 ? "" : "s"}`)}</small><em>${escapeHtml(specs)}</em></span><b>${scoreText(group.laptop_score)}</b></button>${expanded ? `<div class="family-card-variants">${sortedLaptops(items).map(item => compactCard(item)).join("")}</div>` : ""}</article>`;
}
function renderLaptopTable() {
  const all = allLaptops(), matches = filtered(all);
  $("#view-content").className = "catalog-view";
  if (!matches.length) { $("#view-content").innerHTML = emptyState("Nothing matches", "Clear filters or choose another status.", "∅"); return; }
  const toolbar = `<div class="catalog-toolbar"><div class="segmented" role="group" aria-label="Catalog view"><button data-catalog-mode="models" class="${state.catalogMode === "models" ? "active" : ""}" aria-pressed="${state.catalogMode === "models"}">Models</button><button data-catalog-mode="variants" class="${state.catalogMode === "variants" ? "active" : ""}" aria-pressed="${state.catalogMode === "variants"}">Variants</button></div><p>${matches.length} matching exact configuration${matches.length === 1 ? "" : "s"}</p></div>`;
  const head = `<thead><tr>${sortHeader(state.catalogMode === "models" ? "Model" : "Laptop", "model")}${sortHeader("CPU", "cpu")}${sortHeader("GPU", "gpu")}${sortHeader("Laptop Score", "laptop")}${sortHeader("Value Score", "value")}${sortHeader("Effective price", "price")}${sortHeader("Windows", "os")}${sortHeader("Decision", "decision")}</tr></thead>`;
  if (state.catalogMode === "variants") {
    const laptops = sortedLaptops(matches);
    $("#view-content").innerHTML = `${toolbar}<div class="table-wrap desktop-table"><table>${head}<tbody>${laptops.map(item => variantRow(item)).join("")}</tbody></table></div><div class="mobile-cards">${laptops.map((item, index) => compactCard(item, index + 1)).join("")}</div>`;
    return;
  }
  const groups = sortedGroups(familyGroups(matches, all));
  const rows = groups.map(group => `${groupSummary(group)}${state.expandedFamilies.has(group.id) ? sortedLaptops(group.items).map(item => variantRow(item, true)).join("") : ""}`).join("");
  $("#view-content").innerHTML = `${toolbar}<div class="table-wrap desktop-table"><table>${head}<tbody>${rows}</tbody></table></div><div class="mobile-cards">${groups.map(groupCard).join("")}</div>`;
}

function renderPrices() {
  const laptops = allLaptops().filter(item => item.history?.observations || item.historical_references?.length || item.market_snapshot || item.best_offer);
  const research = state.data.market_leads || {};
  const leads = research.leads || [];
  $("#view-content").className = "prices-view";
  const history = laptops.length ? laptops.map(item => {
    const offer = item.best_offer;
    return `<article class="history-card"><header><div><h3>${escapeHtml(item.brand)} ${escapeHtml(item.model)}</h3><small>${escapeHtml(item.sku || "Configuration")}</small></div><button class="text-button" data-details="${escapeHtml(item.id)}">Details</button></header>${offer ? `<div class="price-comparison"><div><small>Listing</small><strong>${money(offer.price ?? offer.total_price)}</strong></div><div><small>Effective</small><strong>${money(offer.effective_price)}</strong></div></div>` : `<p>${item.market_snapshot ? `Snapshot ${money(item.market_snapshot.price_eur)} on ${escapeHtml(item.market_snapshot.date)} · not live` : "Historical references only"}</p>`}<div class="history-stats"><div><strong>${money(item.history?.lowest)}</strong><small>Observed low</small></div><div><strong>${money(item.history?.average)}</strong><small>Average</small></div></div><canvas width="500" height="90" data-history="${escapeHtml(item.id)}" aria-label="Price history chart"></canvas></article>`;
  }).join("") : emptyState("No price history yet", "History starts with the first successful exact offer.", "↗");
  const leadCards = leads.map(lead => `<article class="market-lead ${lead.configuration_status === "configuration_conflict_rejected" ? "conflict" : ""}"><header><div><span class="eyebrow">${escapeHtml(lead.marketplace)} · ${escapeHtml(lead.condition.replaceAll("_", " "))}</span><h3>${escapeHtml(lead.title)}</h3></div><strong>${money(lead.price_eur)}</strong></header><p>${escapeHtml(lead.configuration_status.replaceAll("_", " "))} · ${escapeHtml(lead.confidence)} confidence</p><ul>${lead.downsides.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul><a href="${escapeHtml(lead.url)}" target="_blank" rel="noopener">Recheck listing ↗</a></article>`).join("");
  $("#view-content").innerHTML = `<section class="ranking-section"><div class="section-title"><div><span class="eyebrow">Dated marketplace research · ${escapeHtml(research.as_of || "Unknown")}</span><h3>Second-hand leads</h3></div><p>Ideas only. Recheck the exact SKU, condition, seller, battery, returns, and live price before treating one as an offer.</p></div><div class="market-leads">${leadCards || emptyState("No marketplace leads", "No sufficiently clear second-hand candidates are saved.", "◎")}</div>${research.coverage_notes?.length ? `<div class="coverage-notes">${research.coverage_notes.map(note => `<p>${escapeHtml(note)}</p>`).join("")}</div>` : ""}</section><section class="ranking-section"><div class="section-title"><div><span class="eyebrow">Verified and historical</span><h3>Price observations</h3></div></div><div class="history-grid">${history}</div></section>`;
  $$('canvas[data-history]').forEach(canvas => drawHistory(canvas, laptops.find(item => item.id === canvas.dataset.history)));
}

function drawHistory(canvas, laptop) {
  const values = [laptop.history?.lowest, laptop.history?.average, laptop.history?.highest].filter(value => value != null);
  if (!values.length) return;
  const context = canvas.getContext("2d"), width = canvas.width, height = canvas.height, min = Math.min(...values), max = Math.max(...values);
  context.clearRect(0, 0, width, height); context.strokeStyle = "#245f50"; context.lineWidth = 4; context.beginPath();
  values.forEach((value, index) => { const x = 12 + index * ((width - 24) / Math.max(1, values.length - 1)); const y = height - 12 - ((value - min) / Math.max(1, max - min)) * (height - 24); index ? context.lineTo(x, y) : context.moveTo(x, y); }); context.stroke();
}

function renderSources() {
  const sources = state.data.source_health || [];
  $("#view-content").className = "source-grid";
  $("#view-content").innerHTML = sources.length ? sources.map(source => `<article class="source-card"><header><h3>${escapeHtml(source.source)}</h3><span class="status-dot ${escapeHtml(source.status)}" title="${escapeHtml(source.status)}"></span></header><p>${escapeHtml(source.status.replaceAll("_", " "))} · ${source.offers_found || 0} offers found</p><p>Last attempt: ${formatDate(source.last_attempt)}${source.error ? `<br>${escapeHtml(source.error)}` : ""}</p><a href="${escapeHtml(source.url)}" target="_blank" rel="noopener">Open source ↗</a></article>`).join("") : emptyState("No source run yet", "The first automated run will populate source health.", "◉");
}

function idealList(items) {
  return `<ul>${(items || []).map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function idealConfiguration(items) {
  const labels = { memory_storage: "Memory and storage", build_cooling: "Build and cooling", battery_charging: "Battery and charging", camera_security_ports: "Camera, security, and ports" };
  return `<dl class="detail-grid">${Object.entries(items || {}).map(([key, value]) => `<div><dt>${escapeHtml(labels[key] || key.replaceAll("_", " "))}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}</dl>`;
}

function idealBriefText(ideal) {
  const section = (title, items) => items?.length ? `\n\n${title}:\n- ${items.join("\n- ")}` : "";
  const configuration = Object.entries(ideal.ideal_configuration || {}).map(([key, value]) => `${key.replaceAll("_", " ")}: ${value}`);
  return `${ideal.title || "My ideal laptop brief"}\n\n${ideal.summary || ""}${section("Primary uses", ideal.primary_uses)}${section("Must have", ideal.must_haves)}${section("Ideal configuration", configuration)}${section("Strong preferences", ideal.strong_preferences)}${section("Deal breakers", ideal.deal_breakers)}${section("Trade-off rules", ideal.tradeoff_rules)}${section("Used/refurbished checks", ideal.used_refurbished_checks)}${section("Price guidance", ideal.price_guidance)}${section("How to evaluate an option", ideal.evaluation_output)}\n\nScoring: ${ideal.score_weights || ""}`;
}

function candidateIntakeText() {
  return `Please review this laptop for Laptop Deal Tracker.\n\nProduct link: [paste URL]\nPrice and currency: [if visible]\nCondition: new / open-box / refurbished / used / unknown\nAvailability: [if visible]\nScreenshots attached: yes / no\nWhat attracted me: [optional]\n\nPlease extract the exact manufacturer, model and SKU; verify CPU, GPU, VRAM/TGP, RAM, SSD, keyboard, OS, display, weight, battery, charging, upgradeability, ports, warranty and condition from reliable sources; keep unverified fields Unknown; check SKU aliases and the full configuration fingerprint against the existing database; update an existing record or offer when it matches; create a new master record only when it is genuinely distinct; calculate component indices, the ten criterion scores, Laptop Score, effective price, Value Score and recommendation; and record screenshot prices as dated evidence rather than live offers.`;
}

function renderPreferences() {
  const base = state.data.preferences;
  const costs = allowances();
  const ideal = state.data.ideal_requirements || {};
  $("#view-content").className = "preferences-panel";
  $("#view-content").innerHTML = `<article class="preference-card ideal-brief"><span class="eyebrow">Reusable buying brief</span><h3>${escapeHtml(ideal.title || "My ideal laptop brief")}</h3><p>${escapeHtml(ideal.summary || "Requirements are not available.")}</p><details><summary>Uses and priority checklist</summary><h4>Primary uses</h4>${idealList(ideal.primary_uses)}<h4>Must have</h4>${idealList(ideal.must_haves)}<h4>Strong preferences</h4>${idealList(ideal.strong_preferences)}</details><details><summary>Detailed ideal configuration</summary>${idealConfiguration(ideal.ideal_configuration)}</details><details><summary>Deal breakers and trade-offs</summary><h4>Deal breakers</h4>${idealList(ideal.deal_breakers)}<h4>Trade-off rules</h4>${idealList(ideal.tradeoff_rules)}</details><details><summary>Used/refurbished checks and price guidance</summary><h4>Used/refurbished checklist</h4>${idealList(ideal.used_refurbished_checks)}<h4>Price guidance</h4>${idealList(ideal.price_guidance)}</details><details><summary>Evaluation format and score weights</summary>${idealList(ideal.evaluation_output)}<p><strong>Weights:</strong> ${escapeHtml(ideal.score_weights)}</p></details><div class="preference-actions"><button id="copy-requirements" class="primary-button" type="button">Copy full brief</button><span id="copy-status" role="status"></span></div></article><article class="preference-card"><span class="eyebrow">Candidate intake</span><h3>Add a laptop you find</h3><p>Send a product link, screenshots, or both in a new Codex task. The review extracts listing evidence, researches missing specifications, checks SKU aliases and the full configuration fingerprint for duplicates, and calculates both scores before updating the database.</p><p>Screenshots and unavailable listings are stored as dated evidence. Only a verified current page becomes a live offer.</p><div class="preference-actions"><button id="copy-candidate-template" class="secondary-button" type="button">Copy submission template</button><span id="candidate-copy-status" role="status"></span></div></article><article class="preference-card"><h3>Ready-to-use cost allowances</h3><p>These estimates affect Value Score only. Laptop Score never changes.</p><label>Windows when absent (€)<input id="pref-windows" type="number" min="0" value="${costs.windows}"></label><label>32 GB RAM kit (€)<input id="pref-ram" type="number" min="0" value="${costs.ram_32gb}"></label><label>1 TB SSD (€)<input id="pref-ssd" type="number" min="0" value="${costs.ssd_1tb}"></label><label>Maximum effective price (€)<input id="pref-price" type="number" min="0" value="${escapeHtml(state.preferences.maxPrice ?? base.budget.new_max)}"></label><label><input id="pref-numpad" type="checkbox" ${state.preferences.numpadRequired ? "checked" : ""}> Prefer numpad-only browsing</label><div class="preference-actions"><button id="save-preferences" class="primary-button" type="button">Save on this device</button><button id="reset-preferences" class="secondary-button" type="button">Reset</button></div></article><article class="preference-card"><h3>How scores work</h3><p><strong>Laptop Score</strong> is the fixed weighted hardware score. <strong>Value Score</strong> uses the effective price after Windows and required upgrades. The two are never blended.</p><p>The official Microsoft Windows 11 Home retail reference is ${money(base.cost_allowances.official_windows_reference)}, while your comparison allowance is intentionally lower.</p><div class="preference-actions"><button id="export-preferences" class="secondary-button" type="button">Export JSON</button><label class="secondary-button">Import JSON<input id="import-preferences" type="file" accept="application/json" hidden></label></div></article>`;
}

function componentFor(id) { return (state.data.components || []).find(item => item.id === id); }

function showDetails(id) {
  const record = state.data.laptops.find(item => item.id === id);
  if (!record) return;
  const laptop = decorate(record);
  const offer = laptop.best_offer, breakdown = offer?.price_breakdown;
  const cpu = componentFor(laptop.cpu_component_id), gpu = componentFor(laptop.gpu_profile_id);
  const specs = [
    ["CPU", laptop.cpu], ["GPU", laptop.gpu], ["GPU VRAM / TGP", `${display(laptop.gpu_vram_gb)} GB · ${display(laptop.gpu_tgp_w)} W`],
    ["RAM", laptop.ram_gb ? `${laptop.ram_gb} GB · ${laptop.ram_upgradeable ? "upgradeable" : "fixed/unknown"}` : null], ["Storage", laptop.ssd_gb ? `${laptop.ssd_gb / 1000} TB · second M.2 ${display(laptop.second_m2)}` : null],
    ["Display", [laptop.display_size_in ? `${laptop.display_size_in} in` : null, laptop.resolution, laptop.refresh_rate_hz ? `${laptop.refresh_rate_hz} Hz` : null, laptop.brightness_nits ? `${laptop.brightness_nits} nits` : null].filter(Boolean).join(" · ") || null],
    ["Weight", laptop.weight_kg ? `${laptop.weight_kg} kg` : null], ["Keyboard", laptop.keyboard_layout], ["Numpad", laptop.numpad == null ? null : laptop.numpad ? "Yes" : "No"],
    ["Battery / USB-C", `${display(laptop.battery_wh)} Wh · PD ${display(laptop.usb_c_pd)}`], ["Windows Hello", laptop.windows_hello == null ? null : laptop.windows_hello ? "Yes" : "No"], ["Confidence", laptop.score_confidence || laptop.confidence],
  ];
  const scoreBars = CRITERIA.map(([key, label, weight]) => `<div class="score-row"><div><span>${label}</span><small>${weight}%</small></div><div class="bar"><i style="width:${laptop.criteria_scores?.[key] ?? 0}%"></i></div><strong>${scoreText(laptop.criteria_scores?.[key])}</strong></div>`).join("");
  const priceCard = breakdown ? `<section class="detail-section"><h3>Ready-to-use price</h3><div class="price-breakdown"><div><span>Listing</span><strong>${money(breakdown.listing_price)}</strong></div><div><span>Shipping</span><strong>${money(breakdown.shipping)}</strong></div><div><span>Windows</span><strong>${money(breakdown.windows)}</strong></div><div><span>RAM</span><strong>${money(breakdown.ram)}</strong></div><div><span>SSD</span><strong>${money(breakdown.ssd)}</strong></div><div class="total"><span>Effective total</span><strong>${money(breakdown.effective_price)}</strong></div></div><p>${escapeHtml(osLabel(breakdown.os_status))}${breakdown.blockers.length ? ` · ${escapeHtml(breakdown.blockers.join("; "))}` : ""}</p></section>` : "";
  const snapshotCard = !breakdown && laptop.market_snapshot ? `<section class="detail-section"><h3>Dated price evidence</h3><div class="price-breakdown"><div><span>Observed listing</span><strong>${money(laptop.market_snapshot.price_eur)}</strong></div><div><span>Availability then</span><strong>${escapeHtml(display(laptop.market_snapshot.availability))}</strong></div><div><span>Snapshot Value Score</span><strong>${scoreText(laptop.research_value_snapshot?.value_score)}</strong></div><div class="total"><span>Evidence date</span><strong>${formatDate(laptop.market_snapshot.date)}</strong></div></div><p>This is preserved evidence, not a verified current offer, and is excluded from the live value ranking. ${escapeHtml(laptop.research_value_snapshot?.decision || "Recheck the seller before deciding.")}</p></section>` : "";
  const evidence = laptop.source_urls?.length ? laptop.source_urls.map((url, index) => `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">Evidence ${index + 1} ↗</a>`).join(" · ") : "No linked evidence.";
  $("#dialog-content").innerHTML = `<span class="eyebrow">${escapeHtml(laptop.status)} · ${escapeHtml(laptop.configuration_type || "configuration")}</span><h2>${escapeHtml(laptop.brand)} ${escapeHtml(laptop.model)}</h2><p>${escapeHtml(laptop.variant)}</p><div class="detail-score-head">${scorePair(laptop)}<div><span class="pill ${decisionClass(laptop.decision)}">${escapeHtml(laptop.decision)}</span><p>${escapeHtml(laptop.decision_reason)}</p></div></div><section class="detail-section"><h3>Component comparison</h3><div class="component-cards"><article><small>CPU index</small><strong>${scoreText(cpu?.comparison_score ?? laptop.criteria_scores?.cpu)}</strong><span>${escapeHtml(display(laptop.cpu))}</span></article><article><small>GPU profile index</small><strong>${scoreText(gpu?.comparison_score ?? laptop.criteria_scores?.gpu)}</strong><span>${escapeHtml(display(laptop.gpu))} · ${escapeHtml(display(laptop.gpu_tgp_w))} W</span></article></div></section><section class="detail-section"><h3>Weighted Laptop Score</h3><div class="score-bars">${scoreBars}</div></section>${priceCard}${snapshotCard}<section class="detail-section"><h3>Specifications</h3><dl class="detail-grid">${specs.map(([key, value]) => `<div><dt>${key}</dt><dd>${escapeHtml(display(value))}</dd></div>`).join("")}</dl></section><section class="detail-section"><h3>Current sellers</h3><div class="offer-list">${laptop.offers.length ? laptop.offers.map(item => `<div class="offer-row"><span>${escapeHtml(item.seller)} · ${escapeHtml(item.availability)}<br><small>${escapeHtml(item.configuration_match)} · ${escapeHtml(item.confidence)} confidence</small></span><span><strong>${money(item.effective_price)}</strong> ${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">Open ↗</a>` : ""}</span></div>`).join("") : "<p>No current exact seller offer.</p>"}</div></section><section class="detail-section"><h3>Evidence and long-term risks</h3><p>${evidence}</p>${laptop.regret_flags?.length ? `<ul>${laptop.regret_flags.map(flag => `<li>${escapeHtml(flag)}</li>`).join("")}</ul>` : "<p>No specific regret flags recorded.</p>"}<p>${escapeHtml(laptop.notes || "No notes.")}</p></section>`;
  $("#details-dialog").showModal();
}

function osLabel(status) {
  return { windows_included: "Windows included", no_os: "No OS · add Windows", linux: "Linux included · add Windows", selectable: "Windows selectable", unknown: "Windows status unknown" }[status] || "Windows status unknown";
}
function decisionClass(value) { return String(value || "unrated").toLowerCase().replaceAll(" ", "-"); }
function emptyState(title, text, icon) { return `<article class="empty-state"><span>${icon}</span><h3>${escapeHtml(title)}</h3><p>${escapeHtml(text)}</p></article>`; }

document.addEventListener("click", async event => {
  const nav = event.target.closest("[data-view]");
  if (nav) { state.view = nav.dataset.view; $$('[data-view]').forEach(item => item.classList.toggle("active", item.dataset.view === state.view)); history.replaceState(null, "", `#${state.view}`); renderView(); }
  const details = event.target.closest("[data-details]"); if (details) showDetails(details.dataset.details);
  const catalogMode = event.target.closest("[data-catalog-mode]");
  if (catalogMode) { state.catalogMode = catalogMode.dataset.catalogMode; localStorage.setItem("laptop-tracker-catalog-mode", state.catalogMode); renderView(); }
  const familyToggle = event.target.closest("[data-family-toggle]");
  if (familyToggle) { const id = familyToggle.dataset.familyToggle; state.expandedFamilies.has(id) ? state.expandedFamilies.delete(id) : state.expandedFamilies.add(id); renderView(); }
  const sortHeader = event.target.closest("[data-sort-key]");
  if (sortHeader) { const key = sortHeader.dataset.sortKey; state.sortDirection = state.sort === key ? (state.sortDirection === "asc" ? "desc" : "asc") : naturalDirection(key); state.sort = key; renderFilters(); renderView(); }
  if (event.target.id === "sort-direction") { state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc"; renderFilters(); renderView(); }
  if (event.target.id === "refresh-button") loadData(true);
  if (event.target.id === "filter-toggle") { const filters = $("#filters"); filters.classList.toggle("hidden"); event.target.setAttribute("aria-expanded", String(!filters.classList.contains("hidden"))); }
  if (event.target.id === "clear-filters") { state.filters = { price: "", gpu: "", brand: "", status: "", numpad: false }; ["filter-price","filter-gpu","filter-brand","filter-status"].forEach(id => $(`#${id}`).value = ""); $("#filter-numpad").checked = false; renderFilters(); renderView(); }
  if (event.target.id === "dialog-close") $("#details-dialog").close();
  if (event.target.id === "save-preferences") {
    state.preferences = { ...state.preferences, windowsCost: Number($("#pref-windows").value), ramCost: Number($("#pref-ram").value), ssdCost: Number($("#pref-ssd").value), maxPrice: Number($("#pref-price").value), numpadRequired: $("#pref-numpad").checked };
    localStorage.setItem("laptop-tracker-preferences", JSON.stringify(state.preferences)); renderAll();
  }
  if (event.target.id === "reset-preferences") { localStorage.removeItem("laptop-tracker-preferences"); state.preferences = {}; renderAll(); }
  if (event.target.id === "export-preferences") { const blob = new Blob([JSON.stringify(state.preferences, null, 2)], { type: "application/json" }); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "laptop-tracker-preferences.json"; link.click(); URL.revokeObjectURL(link.href); }
  if (event.target.id === "copy-requirements") {
    const ideal = state.data.ideal_requirements || {};
    await navigator.clipboard.writeText(idealBriefText(ideal));
    $("#copy-status").textContent = "Copied";
  }
  if (event.target.id === "copy-candidate-template") {
    await navigator.clipboard.writeText(candidateIntakeText());
    $("#candidate-copy-status").textContent = "Copied";
  }
});

$("#filters").addEventListener("input", event => {
  if (event.target.id === "filter-price") state.filters.price = event.target.value;
  if (event.target.id === "filter-gpu") state.filters.gpu = event.target.value;
  if (event.target.id === "filter-brand") state.filters.brand = event.target.value;
  if (event.target.id === "filter-status") state.filters.status = event.target.value;
  if (event.target.id === "filter-numpad") state.filters.numpad = event.target.checked;
  if (event.target.id === "sort-by") { if (state.sort !== event.target.value) state.sortDirection = naturalDirection(event.target.value); state.sort = event.target.value; }
  renderFilters(); renderView();
});

$("#view-content").addEventListener("change", async event => {
  if (event.target.id === "import-preferences" && event.target.files[0]) {
    try { state.preferences = JSON.parse(await event.target.files[0].text()); localStorage.setItem("laptop-tracker-preferences", JSON.stringify(state.preferences)); renderAll(); }
    catch { alert("That preferences file is not valid JSON."); }
  }
});

$("#details-dialog").addEventListener("click", event => { if (event.target === event.currentTarget) event.currentTarget.close(); });
const initialView = location.hash.slice(1); if (views[initialView]) state.view = initialView;
$$('[data-view]').forEach(item => item.classList.toggle("active", item.dataset.view === state.view));
loadData();
