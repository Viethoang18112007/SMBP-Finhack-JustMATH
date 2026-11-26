import { escapeHtml, hk, humanize, shortDate } from "../format.js";
import { shownPlaces, statusOf } from "../mapview.js";
import { medalLine } from "../rewards.js";
import { state } from "../store.js";
import { groceriesPanel, isPicked } from "./groceries.js";

function campusName() {
  const found = state.data.campuses.find((c) => c.id === state.data.campus);
  return found ? found.name : "campus";
}

// Campus and distance: two compact selects in one row, so the map stays near the top.
// The campus list comes from the server (state.data.campuses) and is saved per mode.
function mapControls() {
  const campuses = state.data.campuses.map((c) =>
    `<option value="${escapeHtml(c.id)}"${state.data.campus === c.id ? " selected" : ""}>${escapeHtml(c.name)}</option>`
  ).join("");
  const radii = ["0.5", "1", "3", "5", "10"].map((km) =>
    `<option value="${km}"${state.mapRadius === km ? " selected" : ""}>Within ${km} km</option>`
  ).join("");
  return `<div class="map-controls">
      <label class="select"><span class="sr-only">Campus</span><select id="campus" data-campus>${campuses}</select></label>
      <label class="select"><span class="sr-only">Distance from campus</span><select id="radius">${radii}</select></label>
    </div>`;
}

// Eat out (food places and what fits today) or Groceries (cook: recipes, shopping list, trip).
function modeSwitch() {
  const food = state.mapKind === "food";
  const groc = state.mapKind === "grocery";
  return `<div class="seg map-mode" role="group" aria-label="Map mode">`
    + `<button type="button" data-kind="food" class="${food ? "on" : ""}" aria-pressed="${food}">Eat out</button>`
    + `<button type="button" data-kind="grocery" class="${groc ? "on" : ""}" aria-pressed="${groc}">Groceries</button></div>`;
}

// The MVP is about food decisions: the Shopping layer stays available but folded away.
function moreLayers() {
  const kinds = [["food", "Food"], ["shop", "Shopping"]].map(([id, name]) =>
    `<button type="button" data-kind="${id}" class="${state.mapKind === id ? "on" : ""}" aria-pressed="${state.mapKind === id}">${name}</button>`
  ).join("");
  const open = state.mapKind === "shop" ? " open" : "";
  return `<details class="more-layers"${open}><summary>More layers</summary><div class="cats" role="group" aria-label="Layer">${kinds}</div></details>`;
}

// Where the places came from, always on screen.
function sourceLabel(data) {
  if (data.source === "snapshot") {
    return data.fetchedAt ? `Offline snapshot from ${shortDate(data.fetchedAt)}` : "Offline snapshot";
  }
  return "Live OpenStreetMap";
}

// The honesty line, the "could fit" toggle and the label key (food only).
function budgetBlock(data) {
  const left = data.budget.remaining;
  const kinds = [data.budget.rangeRecords ? "menu" : "", data.budget.chainRecords > 0 ? "chain" : ""].filter(Boolean).join(" and ");
  const estimate = `<p class="fit-note">${kinds ? `${kinds[0].toUpperCase()}${kinds.slice(1)} prices: tap Source. ` : ""}Other places: Estimated - not a real menu price.</p>`;
  const legend = `<details class="legend-box"><summary>What the labels mean</summary><div class="legend">
      <span><span class="badge status-fits">Fits</span>verified dish price within one meal's money</span>
      <span><span class="badge status-range_fits">Fits (HK$a to b, menu)</span>the place's own menu range is within one meal's money</span>
      <span><span class="badge status-chain_fits">Fits (chain price)</span>the chain's published meal prices are all within one meal's money</span>
      <span><span class="badge status-range_may">May fit (HK$a to b, menu)</span>menu range: the cheap end fits, the top does not</span>
      <span><span class="badge status-chain_tight">May fit (chain price)</span>the chain's cheaper meals fit, its dearer ones do not</span>
      <span><span class="badge status-range_over">Over (HK$a to b, menu)</span>menu range: even the cheap end is too much</span>
      <span><span class="badge status-chain_over">Over (chain price)</span>even the chain's cheapest meal is above one meal's money</span>
      <span><span class="badge status-estimate">May fit (estimate)</span>price range from the place type</span>
      <span><span class="badge status-unlikely">Likely over (estimate)</span>even the cheap end is too much</span>
      <span><span class="badge status-over">Over budget</span>verified dish price above one meal's money</span>
    </div></details>`;
  if (left == null) {
    return `${estimate}<p class="fit-note">Set your weekly budget to compare.</p>${legend}`;
  }
  // One meal is compared with one meal's share of today's food money, never the whole day.
  const meal = data.budget.perMeal;
  const meals = data.budget.mealsLeft;
  const toggle = `<button type="button" id="fits-only" class="toggle${state.mapFitsOnly ? " on" : ""}" aria-pressed="${state.mapFitsOnly}">Could fit ${hk(Math.max(meal, 0))} a meal</button>`;
  const share = left > 0
    ? `<p class="fit-note meal-share">${hk(left)} left for food today, ${meals} ${meals === 1 ? "meal" : "meals"} to go: about ${hk(meal)} a meal.</p>`
    : `<p class="fit-note">Nothing left for food today, so nothing fits.</p>`;
  return `<div class="fit-head">${toggle}</div>${share}${estimate}${legend}`;
}

// The price on the grey line: a chain's published range, else the estimated range (marked).
function priceText(place) {
  const chain = place.chain;
  if (chain) {
    const span = chain.lowCents === chain.highCents ? hk(chain.lowCents) : `${hk(chain.lowCents)} to ${hk(chain.highCents)}`;
    return `${span} (chain)`;
  }
  const pr = place.priceRange;
  if (pr) return `${hk(pr.min)} to ${hk(pr.max)} per person (menu)`;
  return place.range ? `${place.range}${place.verified ? "" : " (est.)"}` : "";
}

// The source of a menu range or a chain price, with the date it was read, folded under the place
// (a link can't sit inside the row button). The short tag on the row says which kind it is.
function sourceLink(place) {
  const link = sourceText(place);
  return link ? `<details class="place-src-box"><summary>Source</summary>${link}</details>` : "";
}

function sourceText(place) {
  const pr = place.priceRange;
  if (pr) {
    return `<a class="place-src" href="${escapeHtml(pr.sourceUrl)}" target="_blank" rel="noopener noreferrer">Source: ${escapeHtml(pr.sourceName)} menu, read ${escapeHtml(shortDate(pr.checkedOn))}${pr.note ? ` (${escapeHtml(pr.note)})` : ""}</a>`;
  }
  const chain = place.chain;
  if (!chain) return "";
  const url = chain.sources.find((s) => s.startsWith("https://"));
  const check = chain.needsCheck ? ", not yet checked in a shop" : "";
  const text = `Chain price: ${escapeHtml(chain.chain)}, read ${escapeHtml(shortDate(chain.checkedOn))}${check}`;
  return url ? `<a class="place-src" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${text}</a>` : `<span class="place-src">${text}</span>`;
}

function groceryRow(place) {
  const picked = isPicked(place.id) ? " picked" : "";
  const prices = place.chainName ? `${place.chainName} prices` : "prices: estimate";
  const meta = [humanize(place.detail) || "Shop", `${place.distanceKm} km`, prices].join(" · ");
  return `<button type="button" class="place status-shop${picked}" data-key="pl-${escapeHtml(place.id)}" data-place="${escapeHtml(place.id)}" aria-pressed="${Boolean(picked)}">`
    + `<span class="dot status-shop" aria-hidden="true"></span>`
    + `<span class="place-body"><span class="place-name">${escapeHtml(place.name)}</span>`
    + `<span class="tag">${escapeHtml(meta)}</span><span class="pick-mark">${picked ? "Comparing" : "Tap to compare"}</span></span></button>`;
}

function placeRow(place) {
  if (state.mapKind === "grocery") return groceryRow(place);
  const on = place.id === state.selectedId ? " on" : "";
  const status = statusOf(place);
  const badge = place.label ? `<span class="badge status-${status}">${escapeHtml(place.label)}</span>` : "";
  // Menu and chain rows: the badge and the folded source say it all. Estimates keep their
  // one-line warning (place.why: "Estimated ... - not a real menu price"), which has the range.
  const estimate = !place.priceRange && !place.chain && !place.verified;
  const why = estimate && place.why ? `<span class="why status-${status}">${escapeHtml(place.why)}</span>` : "";
  const twice = (estimate && why) || (place.priceRange && place.label && place.label.includes("HK$"));
  const price = twice ? "" : priceText(place);
  const meta = [humanize(place.detail) || "OpenStreetMap", `${place.distanceKm} km`, price]
    .filter(Boolean).join(" · ");
  const source = sourceLink(place);
  // Shown for the place picked on the list or the map (mapview.selectPlace). Food only, with a budget.
  const canLog = state.map.kind === "food" && state.view.ready;
  const log = canLog
    ? `<button type="button" class="ghost small log-meal" data-log-place="${escapeHtml(place.id)}"${place.id === state.selectedId ? "" : " hidden"}>Log a meal here</button>`
    : "";
  return `<button type="button" class="place status-${status}${on}" data-key="pl-${escapeHtml(place.id)}" data-place="${escapeHtml(place.id)}" aria-pressed="${place.id === state.selectedId}">`
    + `<span class="dot status-${status}" aria-hidden="true"></span>`
    + `<span class="place-body"><span class="place-name">${escapeHtml(place.name)}</span>`
    + `<span class="tag">${escapeHtml(meta)}</span>${badge}${why}</span></button>${log}${source}`;
}

export function mapScreen() {
  const data = state.mapLoading ? null : state.map;
  const controls = `${modeSwitch()}${mapControls()}`;
  if (!data) {
    const loading = state.data.mode === "demo" ? "Loading the offline snapshot…" : "Loading places from OpenStreetMap…";
    const message = state.mapLoading ? loading : (state.error || loading);
    const role = !state.mapLoading && state.error ? ' role="alert"' : ' role="status"';
    const cls = state.mapLoading ? "explain loading" : "explain";
    return `${controls}<div class="map-wait"><div class="${cls}"${role}>${escapeHtml(message)}</div></div>`;
  }
  const places = shownPlaces(data);
  const noun = data.kind === "food" ? "food places" : data.kind === "grocery" ? "grocery stores" : "shops";
  let rows;
  if (places.length) rows = places.map(placeRow).join("");
  else if (data.places.length) rows = `<p class="empty-line">Nothing nearby fits today. Turn off "Could fit" to see all.</p>`;
  else rows = `<p class="empty-line">OpenStreetMap has no named ${noun} within ${data.radiusKm} km.</p>`;
  const count = data.total > data.shown
    ? `Nearest ${places.length} of ${data.total} ${noun}`
    : `${places.length} ${noun}`;
  const budget = data.kind === "grocery" ? groceriesPanel() : data.budget ? budgetBlock(data) : "";
  return `${controls}
    <div id="osm-map" role="region" aria-label="Map of places around ${escapeHtml(data.center.name || campusName())}"></div>
    <div class="source" id="map-source">${escapeHtml(sourceLabel(data))} · © OpenStreetMap contributors</div>
    ${budget}
    ${data.kind === "food" ? medalLine() : ""}
    <div class="list-head"><h2 class="title">${count}</h2></div>
    <div class="list">${rows}</div>
    ${moreLayers()}`;
}
