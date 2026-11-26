// Groceries mode of the Map tab: what to cook, what to buy, what it costs, and the trip.
//
// The server does the sums (backend/ssust/groceries.py): real supermarket shelf prices from the
// Consumer Council's Online Price Watch (with the date), "price unknown" when an ingredient is
// not in that list, and trip estimates from the official taxi table and the MTR fare table.
// This panel only collects the choices and shows the answer. It repaints itself (not the whole
// screen), so the map stays where it is. Tapping a store in the list or on the map picks it for
// the comparison (two at most).

import { api } from "../api.js";
import { setHtml } from "../closers.js";
import { escapeHtml, hk, shortDate } from "../format.js";
import { state } from "../store.js";

const g = {
  catalogue: null,
  recipe: "tomato_egg_rice",
  servings: 1,
  mode: "walk",
  fare: "student",
  roundTrip: true,
  pantry: false,
  stores: [], // picked store ids, oldest first
  origin: null, // {lat, lng} from "My location", else the campus
  locating: false,
  plan: null,
  error: "",
  busy: false,
};
let planToken = 0;
let planTimer = 0;

export function isPicked(id) {
  return g.stores.includes(id);
}

const MODE_NAME = { walk: "Walk", mtr: "MTR or bus", taxi: "Taxi" };
const UNIT = { g: "g", ml: "ml", pc: "", pack: " pack", bulb: " bulb", head: " head", slice: " slices" };

function qtyText(item) {
  const [a, b] = item.qty.split("/").map(Number);
  const value = b ? a / b : a;
  const shown = Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/0+$/, "");
  return `${shown}${UNIT[item.unit] ?? ` ${item.unit}`}`;
}

function seg(name, value, options) {
  return `<div class="seg small" role="group" aria-label="${escapeHtml(name)}">${options.map(([id, label]) =>
    `<button type="button" class="${value === id ? "on" : ""}" aria-pressed="${value === id}" data-groc-${name.toLowerCase().replace(/\s+/g, "-")}="${id}">${escapeHtml(label)}</button>`).join("")}</div>`;
}

function itemRow(item) {
  if (item.status === "unknown") {
    return `<tr class="unknown"><td>${escapeHtml(item.name)}</td><td class="num">${qtyText(item)}</td><td colspan="2"><span class="badge status-unknown">price unknown</span> not in the supermarket price list</td></tr>`;
  }
  const p = item.product;
  const where = item.status === "chain" ? "" : item.status === "other_chain"
    ? ` <span class="groc-note">(not listed here: price at ${escapeHtml(item.chain)})</span>`
    : ` <span class="groc-note">(typical supermarket price)</span>`;
  const cost = item.pantry
    ? `<span class="groc-note">pantry, this meal uses ${hk(item.usedCents)}</span>`
    : `<strong class="num">${hk(item.buyCents)}</strong>${item.packs > 1 ? ` <span class="groc-note">${item.packs} packs</span>` : ""}`;
  return `<tr${item.pantry ? ' class="pantry"' : ""}><td>${escapeHtml(item.name)}</td><td class="num">${qtyText(item)}</td>`
    + `<td>${escapeHtml(p.brand)} ${escapeHtml(p.name)}${where}</td><td class="num">${cost}</td></tr>`;
}

function basketHtml(basket) {
  const unknown = basket.unknown.length
    ? `<p class="groc-note">+ ${basket.unknown.length} item${basket.unknown.length === 1 ? "" : "s"} with price unknown (${escapeHtml(basket.unknown.join(", "))}): not in the total.</p>`
    : "";
  return `<table class="groc-table"><thead><tr><th>Ingredient</th><th>Need</th><th>Product</th><th>Cost</th></tr></thead>
      <tbody>${basket.items.map(itemRow).join("")}</tbody></table>
    <div class="groc-total"><span>Groceries${basket.includePantry ? " (pantry included)" : ""}</span><strong class="num">${hk(basket.totalCents)}</strong></div>${unknown}`;
}

function tripHtml(trip) {
  const mode = MODE_NAME[trip.mode];
  const time = trip.minutes != null ? `, about ${trip.minutes} min each way` : "";
  const src = trip.sourceUrl
    ? ` <a class="place-src" href="${escapeHtml(trip.sourceUrl)}" target="_blank" rel="noopener noreferrer">Source: ${escapeHtml(trip.source)}, read ${escapeHtml(shortDate(trip.checkedOn))}</a>`
    : "";
  const check = trip.needsCheck ? " Not checked for your exact route." : "";
  return `<div class="groc-trip"><span>${mode}${trip.roundTrip ? ", there and back" : ", one way"} (${escapeHtml(trip.streetKm)} km by street${time})</span>`
    + `<strong class="num">${trip.cents ? hk(trip.cents) : "Free"}</strong></div>`
    + `<p class="groc-note"><span class="badge status-estimate">Estimate</span> ${escapeHtml(trip.note)}${check}${src}</p>`;
}

function storeCard(store, best) {
  const prices = store.chainName ? `${escapeHtml(store.chainName)} shelf prices` : "Prices of the big supermarkets: this store may differ (estimate)";
  return `<section class="groc-store${best ? " best" : ""}" aria-label="${escapeHtml(store.name)}">
      <div class="groc-store-head"><strong>${escapeHtml(store.name)}</strong><span class="tag">${store.distanceKm} km · ${prices}</span></div>
      ${basketHtml(store.basket)}
      ${tripHtml(store.trip)}
      <div class="groc-total grand"><span>Total = groceries + trip</span><strong class="num">${hk(store.totalCents)}</strong></div>
    </section>`;
}

function fitHtml(plan) {
  const fit = plan.fit;
  if (fit.status === "no_budget") return `<p class="fit-note">Set your weekly budget to compare with Main meals.</p>`;
  const cheapest = fit.mainLeftCents - fit.leftCents;
  const line = fit.status === "fits"
    ? `Fits: ${hk(cheapest)} of the ${hk(fit.mainLeftCents)} left in Main meals this week (${hk(fit.leftCents)} would stay).`
    : `Over: ${hk(cheapest)} is ${hk(-fit.leftCents)} more than the ${hk(fit.mainLeftCents)} left in Main meals this week.`;
  return `<p class="groc-fit ${fit.status}" role="status">${escapeHtml(line)}</p>`;
}

function resultHtml() {
  const plan = g.plan;
  if (g.error) return `<p class="error" role="alert">${escapeHtml(g.error)}</p>`;
  if (!plan) return `<p class="explain loading" role="status">Pricing the shopping list…</p>`;
  const recipe = plan.recipe;
  const src = plan.prices;
  const source = `<p class="groc-note">Source: <a class="place-src" href="${escapeHtml(src.sourceUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(src.source)}</a>, read ${escapeHtml(shortDate(src.checkedOn))}. ${escapeHtml(src.note)}</p>`;
  const verdict = plan.compare ? `<p class="groc-verdict" role="status"><strong>Worth going?</strong> ${escapeHtml(plan.compare.text)}</p>` : "";
  const body = plan.stores.length
    ? plan.stores.map((s) => storeCard(s, plan.compare && plan.compare.best === s.id)).join("")
    : `<section class="groc-store"><div class="groc-store-head"><strong>Typical supermarket prices</strong><span class="tag">Tap a store on the map or in the list to price it there and add the trip</span></div>${basketHtml(plan.basket)}</section>`;
  return `${fitHtml(plan)}${verdict}${body}${source}
    <details class="more"><summary>How to cook it (${recipe.minutes} min)</summary><p>${escapeHtml(recipe.steps)}</p></details>
    <div data-rate-slot="groceries" data-context="recipe:${escapeHtml(recipe.id)}" data-question="Is this cost realistic?"></div>`;
}

function pickedHtml() {
  const names = new Map(((state.map && state.map.places) || []).map((p) => [p.id, p.name]));
  if (!g.stores.length) return `<p class="groc-note">Tap up to two stores (list or map) to compare their baskets and trips.</p>`;
  return `<div class="groc-picked">${g.stores.map((id) => `<span class="chip">${escapeHtml(names.get(id) || id)}<button type="button" class="chip-x" data-groc-unpick="${escapeHtml(id)}" aria-label="Remove ${escapeHtml(names.get(id) || "store")}">✕</button></span>`).join("")}</div>`;
}

function formHtml() {
  const recipes = (g.catalogue ? g.catalogue.recipes : []).map((r) =>
    `<option value="${escapeHtml(r.id)}"${r.id === g.recipe ? " selected" : ""}>${escapeHtml(r.name)} (${r.minutes} min)</option>`).join("");
  const from = g.origin ? "My location" : "Campus";
  return `<div class="groc-form">
      <label class="label" for="groc-recipe">What to cook</label>
      <label class="select"><select id="groc-recipe" data-groc-recipe>${recipes}</select></label>
      <div class="groc-row">
        <span class="label">Servings</span>
        <div class="stepper"><button type="button" class="ghost small" data-groc-servings="-1" aria-label="One serving less"${g.servings <= 1 ? " disabled" : ""}>−</button>
          <strong class="num" aria-live="polite">${g.servings}</strong>
          <button type="button" class="ghost small" data-groc-servings="1" aria-label="One serving more"${g.servings >= 10 ? " disabled" : ""}>+</button></div>
      </div>
      <button type="button" class="toggle switch-row" data-groc-pantry aria-pressed="${g.pantry}"><span>Buy pantry items too (oil, sauces, salt)</span><span class="switch" aria-hidden="true"></span></button>
      <div class="label">Getting there from: ${from}</div>
      <div class="groc-row wrap">
        <button type="button" class="ghost small" data-groc-origin="campus"${g.origin ? "" : " disabled"}>Campus</button>
        <button type="button" class="ghost small" data-groc-origin="here"${g.locating ? " disabled" : ""}>${g.locating ? "Locating…" : "My location"}</button>
      </div>
      ${seg("Mode", g.mode, [["walk", "Walk"], ["mtr", "MTR or bus"], ["taxi", "Taxi"]])}
      ${g.mode === "mtr" ? seg("Fare", g.fare, [["student", "Student"], ["adult", "Adult"]]) : ""}
      <button type="button" class="toggle switch-row" data-groc-round aria-pressed="${g.roundTrip}"><span>There and back</span><span class="switch" aria-hidden="true"></span></button>
      ${pickedHtml()}
    </div>`;
}

export function groceriesPanel() {
  return `<section class="card groceries" id="groc-panel" aria-label="Groceries">${panelBody()}</section>`;
}

function panelBody() {
  if (!g.catalogue) return `<p class="explain loading" role="status">Loading recipes…</p>`;
  return `${formHtml()}<div class="groc-result" aria-live="polite">${resultHtml()}</div>`;
}

function paint() {
  const box = document.getElementById("groc-panel");
  if (box && setHtml(box, panelBody())) document.dispatchEvent(new CustomEvent("ssust:rate-slots"));
  document.querySelectorAll("[data-place]").forEach((row) => row.classList.toggle("picked", isPicked(row.dataset.place)));
}

async function plan() {
  const token = ++planToken;
  const body = { recipe: g.recipe, servings: g.servings, stores: g.stores, radius: state.mapRadius, mode: g.mode,
    fare: g.fare, roundTrip: g.roundTrip, includePantry: g.pantry };
  if (g.origin) body.origin = g.origin;
  try {
    const answer = await api("/api/groceries/plan", body);
    if (token !== planToken) return;
    g.plan = answer;
    g.error = "";
  } catch (err) {
    if (token !== planToken) return;
    g.error = err.message;
    g.stores = err.message.includes("not on the map") ? [] : g.stores;
  }
  paint();
}

function replan() {
  g.plan = g.plan && !g.error ? g.plan : null;
  paint();
  clearTimeout(planTimer);
  planTimer = setTimeout(plan, 120);
}

// Called by loadMap when the Groceries mode opens (or the campus or radius changes).
export async function openGroceries() {
  g.stores = g.stores.filter((id) => (state.map && state.map.places || []).some((p) => p.id === id));
  if (!g.catalogue) {
    try {
      g.catalogue = await api("/api/groceries");
    } catch (err) {
      g.error = err.message;
    }
  }
  paint();
  if (g.catalogue) plan();
}

function locate() {
  if (!navigator.geolocation) {
    g.error = "This browser cannot share a location. The campus is used instead.";
    paint();
    return;
  }
  g.locating = true;
  paint();
  navigator.geolocation.getCurrentPosition((pos) => {
    g.locating = false;
    g.origin = { lat: pos.coords.latitude, lng: pos.coords.longitude };
    g.error = "";
    replan();
  }, () => {
    g.locating = false;
    g.error = "Location not shared. The campus is used instead.";
    g.origin = null;
    paint();
    setTimeout(plan, 1500);
  }, { timeout: 10000, maximumAge: 60000 });
}

document.addEventListener("click", (event) => {
  if (state.screen !== "map" || state.mapKind !== "grocery") return;
  const row = event.target.closest("[data-place]");
  if (row && !event.target.closest(".place-src-box")) {
    const id = row.dataset.place;
    g.stores = isPicked(id) ? g.stores.filter((s) => s !== id) : [...g.stores, id].slice(-2);
    replan();
    return;
  }
  const el = event.target.closest("[data-groc-servings], [data-groc-pantry], [data-groc-round], [data-groc-mode], [data-groc-fare], [data-groc-origin], [data-groc-unpick]");
  if (!el) return;
  const d = el.dataset;
  if (d.grocServings) g.servings = Math.min(10, Math.max(1, g.servings + Number(d.grocServings)));
  else if ("grocPantry" in d) g.pantry = !g.pantry;
  else if ("grocRound" in d) g.roundTrip = !g.roundTrip;
  else if (d.grocMode) g.mode = d.grocMode;
  else if (d.grocFare) g.fare = d.grocFare;
  else if (d.grocUnpick) g.stores = g.stores.filter((s) => s !== d.grocUnpick);
  else if (d.grocOrigin === "here") {
    locate();
    return;
  } else if (d.grocOrigin === "campus") g.origin = null;
  g.error = "";
  replan();
});

// Pins on the map pick stores too (mapview.js sends this when a grocery pin is tapped).
document.addEventListener("ssust:pick-store", (event) => {
  const id = event.detail;
  if (!id || isPicked(id)) return;
  g.stores = [...g.stores, id].slice(-2);
  replan();
});

document.addEventListener("change", (event) => {
  if (event.target.matches?.("[data-groc-recipe]")) {
    g.recipe = event.target.value;
    replan();
  }
});
