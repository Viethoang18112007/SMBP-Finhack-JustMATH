// The Leaflet map. window.L comes from the vendored leaflet.js, loaded before the modules.
//
// Food places are coloured by their status: verified fits (large, solid green), verified over
// budget (solid red), chain prices (solid, a ring), estimates (hollow, dashed). Shops are plain
// blue dots.

import { escapeHtml, humanize } from "./format.js";
import { state } from "./store.js";

// Pins by status (fit.rank_places). Verified prices are solid; estimates are hollow and dashed,
// so an estimate never looks like a verified price.
const COLOR = {
  fits: "#1a7f4b",
  over: "#b42318",
  verified: "#1d4f91",
  estimate: "#a15c07",
  unlikely: "#667085",
  unknown: "#667085",
  shop: "#2f6fed",
  // Price ranges read on the place's own menu: solid, like verified prices.
  range_fits: "#1a7f4b",
  range_may: "#a15c07",
  range_over: "#b42318",
  range: "#1d4f91",
  chain_fits: "#2e9b62",
  chain_tight: "#d08a12",
  chain_over: "#d6453b",
  chain: "#4a78c2",
};
const VERIFIED = new Set(["fits", "over", "verified", "range_fits", "range_may", "range_over", "range"]);
// A chain's published meal range: solid like a real price, with a white ring so it never
// looks like a verified dish price or a place's own menu.
const CHAIN = new Set(["chain_fits", "chain_tight", "chain_over", "chain"]);
// What the "Could fit today" toggle keeps.
const COULD_FIT = new Set(["fits", "range_fits", "chain_fits", "range_may", "chain_tight", "estimate"]);

export function statusOf(place) {
  return place.status || "shop";
}

// The places drawn on the map and in the list. The toggle keeps the places that could fit today:
// verified fits and estimates that may fit.
export function shownPlaces(data) {
  if (!data) return [];
  if (data.budget && data.budget.remaining != null && state.mapFitsOnly) {
    return data.places.filter((place) => COULD_FIT.has(place.status));
  }
  return data.places;
}

function pinStyle(place, selected) {
  const status = statusOf(place);
  const color = COLOR[status] || COLOR.unknown;
  const chain = CHAIN.has(status);
  const solid = VERIFIED.has(status) || status === "shop" || chain;
  const ring = chain ? "#ffffff" : color;
  return {
    radius: selected ? 10 : status === "fits" || status === "chain_fits" ? 8 : 6,
    color: selected ? "#172033" : ring,
    weight: selected ? 3 : chain ? 2 : solid ? 1 : 2.5,
    dashArray: solid ? null : "3 3",
    fillColor: solid ? color : "#ffffff",
    fillOpacity: solid ? 0.95 : 0.9,
  };
}

let liveMap = null;
let markers = new Map();

export function clearMap() {
  markers = new Map();
  if (!liveMap) return;
  liveMap.remove();
  liveMap = null;
}

function placeById(id) {
  return shownPlaces(state.map).find((place) => place.id === id);
}

function popup(place) {
  const status = place.label ? `<br><strong>${escapeHtml(place.label)}</strong>` : "";
  const why = place.why ? `<br>${escapeHtml(place.why)}` : "";
  return `<strong>${escapeHtml(place.name)}</strong><br>${escapeHtml(humanize(place.detail))}<br>${place.distanceKm} km${status}${why}`;
}

export function selectPlace(id) {
  state.selectedId = id;
  document.querySelectorAll("[data-place]").forEach((el) => {
    el.classList.toggle("on", el.dataset.place === id);
  });
  document.getElementById("osm-map")?.scrollIntoView({ block: "nearest" });
  const marker = markers.get(id);
  const place = placeById(id);
  if (!liveMap || !marker || !place) return;
  markers.forEach((item, itemId) => {
    const other = placeById(itemId);
    if (other) item.setStyle(pinStyle(other, itemId === id));
  });
  liveMap.flyTo([place.lat, place.lng], 17, { duration: 0.45 });
  marker.openPopup();
}

// The map was hidden (home screen) or its box changed size: Leaflet must measure it again.
export function refreshMapSize() {
  if (liveMap) liveMap.invalidateSize();
}

export function mountMap() {
  const el = document.getElementById("osm-map");
  if (!el || !state.map || state.mapLoading || !window.L) return;
  const center = [state.map.center.lat, state.map.center.lng];
  const map = window.L.map(el, { zoomControl: true }).setView(center, 15);
  liveMap = map;
  window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    // The page sends no Referer; OSM's tile policy needs one on tile requests.
    referrerPolicy: "strict-origin-when-cross-origin",
  }).addTo(map);
  window.L.circle(center, {
    radius: state.map.radiusKm * 1000,
    color: "#1d4f91",
    weight: 1,
    fillOpacity: 0.06,
  }).addTo(map);
  const bounds = [center];
  // Draw verified fits last so those pins sit on top.
  const places = shownPlaces(state.map).slice().reverse();
  places.forEach((place) => {
    bounds.push([place.lat, place.lng]);
    const marker = window.L.circleMarker([place.lat, place.lng], pinStyle(place, place.id === state.selectedId))
      .bindPopup(popup(place))
      .addTo(map);
    marker.on("click", () => selectPlace(place.id));
    markers.set(place.id, marker);
  });
  const selected = state.selectedId && placeById(state.selectedId);
  if (selected && markers.has(selected.id)) {
    map.setView([selected.lat, selected.lng], 17);
    markers.get(selected.id).openPopup();
  } else if (bounds.length > 1) {
    map.fitBounds(bounds, { padding: [18, 18] });
  }
  setTimeout(() => map.invalidateSize(), 0);
}
