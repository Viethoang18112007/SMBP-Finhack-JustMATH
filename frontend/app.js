const CATEGORIES = [
  ["main", "Main meal"],
  ["snack", "Snack"],
  ["fixed", "Fixed bill"],
  ["experience", "Experience"],
  ["development", "Development"],
];
const FUND_FIELDS = [
  ["main", "Main meals this week (HK$)"],
  ["snack", "Snacks this week (HK$)"],
  ["fixed", "Fixed bills (HK$)"],
  ["experience", "Experience (HK$)"],
  ["development", "Development (HK$)"],
  ["savings", "Long-term savings (HK$)"],
];
const FUND_NAME = {
  main: "Main meals",
  snack: "Snacks",
  fixed: "Fixed Bills",
  experience: "Experience",
  development: "Development",
  savings: "Long-term Savings",
};

const state = {
  data: null,
  view: null,
  screen: "today",
  day: null,
  draft: { amount: "", category: "main", note: "" },
  error: "",
  sheet: null,
  showNotice: false,
  mapKind: "food",
  mapRadius: "3",
  map: null,
  mapLoading: false,
  selectedId: "",
};

function hk(cents) {
  if (cents == null || Number.isNaN(cents)) return "—";
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(Math.round(cents));
  const dollars = Math.floor(abs / 100);
  const rem = abs % 100;
  const body = dollars.toLocaleString("en-HK");
  return rem === 0 ? `${sign}HK$${body}` : `${sign}HK$${body}.${String(rem).padStart(2, "0")}`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function dayLabel(iso) {
  const names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return `${names[dt.getUTCDay()]} ${d} Nov`;
}

function parseAmount(raw) {
  const cleaned = String(raw).replace(/hk\$/i, "").replace(/,/g, "").trim();
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  const [d, c = ""] = cleaned.split(".");
  const cents = Number(d) * 100 + Number(c.padEnd(2, "0"));
  if (cents <= 0 || cents > 100000000) return null;
  return cents;
}

function labelOf(category) {
  return CATEGORIES.find(([id]) => id === category)?.[1] || category;
}

function paymentsOn(date) {
  return state.data.payments.filter((p) => p.date === date);
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try {
    data = await res.json();
  } catch (err) {
    data = {};
  }
  if (!res.ok) throw new Error(data.error || "The server refused that.");
  return data;
}

function applyState(payload, extra) {
  state.data = payload;
  state.view = payload.view;
  if (extra) Object.assign(state, extra);
}

function render() {
  clearMap();
  const root = document.getElementById("screen");
  const nav = document.getElementById("nav");
  if (!state.view) {
    root.innerHTML = `<div class="card"><div class="explain">Waiting for the SSUST server.</div></div>`;
    return;
  }
  root.innerHTML = screens[state.screen](state.view);
  nav.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.screen === state.screen);
  });
  const sheet = document.getElementById("sheet");
  sheet.innerHTML = state.sheet ? sheetHtml(state.sheet) : "";
  sheet.hidden = !state.sheet;
  bind();
}

function fundRows(view) {
  const funds = view.fundsNow;
  const food = funds.main + funds.snack;
  const rows = [
    ["Food and Drinks", food, `Main meals ${hk(funds.main)} · Snacks ${hk(funds.snack)}`],
    ["Fixed Bills", funds.fixed, "No hole"],
    ["Experience", funds.experience, "Flexible"],
    ["Development", funds.development, "Flexible"],
    ["Long-term Savings", funds.savings, "Heavy hole"],
  ];
  return rows.map(([name, amount, note]) =>
    `<div class="row"><div><strong>${name}</strong><div class="tag">${note}</div></div><div>${hk(Math.max(amount, 0))}</div></div>`
  ).join("");
}

function todayScreen(view) {
  if (!view.ready) {
    return `<div class="card"><div class="kicker">Five funds</div>
      <p class="explain">Type the five ZUNO funds to start. Food and Drinks is split across the days left, including today.</p>
      <button class="primary" id="go-settings" type="button">Set the five funds</button></div>`;
  }
  const ratio = view.allowance > 0 ? Math.min(view.spentToday / view.allowance, 1) : 1;
  const tone = view.overToday ? "over" : view.notice ? "near" : "";
  const notice = state.showNotice && view.notice
    ? `<div class="notice">Most of today is used. ${hk(view.spentToday)} of ${hk(view.allowance)}.</div>`
    : "";
  const items = paymentsOn(state.data.today);
  return `${notice}
    <div class="card">
      <div class="kicker">${escapeHtml(dayLabel(state.data.today))} · ${view.daysLeft} days left</div>
      <div class="big">${hk(Math.max(view.todayRemaining, 0))}</div>
      <div class="explain">left of today's ${hk(view.allowance)}. Food and Drinks ${hk(view.lifeAtStart)} ÷ ${view.daysLeft} days. Tomorrow is ${hk(view.tomorrow)}.</div>
      <div class="bar ${tone}"><span style="width:${Math.round(ratio * 100)}%"></span></div>
    </div>
    <div class="card"><div class="kicker">Five funds</div><div class="list" style="margin-top:8px">${fundRows(view)}</div></div>
    <div class="stack" style="margin-bottom:12px">
      <button class="primary" id="add" type="button">Add a payment</button>
    </div>
    <div class="kicker">Today</div>
    <div class="list" style="margin-top:8px">${items.length ? items.map(paymentRow).join("") : `<div class="explain">Nothing logged today yet.</div>`}</div>`;
}

function addScreen() {
  const cats = CATEGORIES.map(([id, name]) =>
    `<button type="button" data-cat="${id}" class="${state.draft.category === id ? "on" : ""}">${name}</button>`
  ).join("");
  return `<div class="card">
      <div class="kicker">Amount</div>
      <input class="amount" id="amount" inputmode="decimal" placeholder="0" value="${escapeHtml(state.draft.amount)}" aria-label="Amount in Hong Kong dollars">
      <div class="error" id="err">${escapeHtml(state.error)}</div>
      <div class="kicker">Fund</div>
      <div class="cats">${cats}</div>
      <div class="explain">Main meals and Snacks use today's line. A gap comes out of Snacks, then Experience or Development, then Long-term Savings. Fixed Bills does not borrow.</div>
      <input class="note" id="note" maxlength="40" placeholder="Note, optional" value="${escapeHtml(state.draft.note)}">
      <div class="stack">
        <button class="primary" id="save" type="button">Save</button>
        <button class="ghost" id="cancel-add" type="button">Cancel</button>
      </div>
    </div>`;
}

function weekScreen(view) {
  const buttons = view.dates.map((date) => {
    const spent = sumOn(date);
    let tone = "";
    if (date === state.data.today) tone = view.overToday ? "over" : view.notice ? "near" : "under";
    const mark = date === state.data.today ? "Today" : date > state.data.today ? "Ahead" : dayLabel(date).slice(0, 3);
    return `<div class="row"><button class="day ${tone} ${date === state.data.today ? "today" : ""}" type="button" data-day="${date}">
      <span><strong>${escapeHtml(dayLabel(date))}</strong><br><span class="tag">${mark}</span></span>
      <span>${spent ? hk(spent) : "—"}</span>
    </button></div>`;
  }).join("");
  return `<div class="card"><div class="kicker">This SAMPLE week</div>
    <div class="explain">Mon 9 Nov to Sun 15 Nov. Colour is only on today: green under 80%, amber from 80% to the line, red after the line.</div></div>
    <div class="list">${buttons}</div>`;
}

function dayScreen() {
  const date = state.day || state.data.today;
  const items = paymentsOn(date);
  return `<div class="card"><div class="kicker">${escapeHtml(dayLabel(date))}</div>
    ${items.length ? `<div class="list">${items.map(paymentRow).join("")}</div>` : `<div class="explain">No payments on this day.</div>`}
    <div class="stack" style="margin-top:12px"><button class="ghost" id="back-week" type="button">Back to the week</button></div>
  </div>`;
}

function settingsScreen(view) {
  const fields = FUND_FIELDS.map(([id, name]) => {
    const cents = view.fundsAtStart[id];
    const value = cents == null ? "" : String(cents / 100);
    return `<div class="field"><label for="${id}">${name}</label><input id="${id}" inputmode="decimal" value="${value}"></div>`;
  }).join("");
  return `<div class="card"><div class="kicker">Five funds</div>
    ${fields}
    <button class="primary" id="apply" type="button">Use these numbers</button>
    <div class="error">${escapeHtml(state.error)}</div>
  </div>
  <div class="stack">
    <button class="ghost" data-mode="sample" type="button">SAMPLE week · five funds</button>
    <button class="ghost" data-mode="empty" type="button">Empty week</button>
    <button class="ghost" data-mode="over" type="button">Week already over</button>
  </div>
  <p class="explain">Current mode: ${escapeHtml(state.data.mode)}. Food and Drinks now: ${hk(view.lifeNow)}. Long-term Savings: ${hk(view.fundsNow.savings)}.</p>`;
}

function paymentRow(p) {
  const from = p.from || {};
  const tags = [];
  if (from.snack > 0 && p.category !== "snack") tags.push(`${hk(from.snack)} from Snacks`);
  if (from.experience > 0 && p.category !== "experience") tags.push(`${hk(from.experience)} from Experience`);
  if (from.development > 0 && p.category !== "development") tags.push(`${hk(from.development)} from Development`);
  if (from.savings > 0) tags.push(`${hk(from.savings)} from Long-term Savings`);
  if (p.uncovered > 0) tags.push(`${hk(p.uncovered)} stays outside the funds`);
  const extra = tags.map((tag) => `<div class="tag">${escapeHtml(tag)}</div>`).join("");
  return `<div class="row"><div><strong>${escapeHtml(labelOf(p.category))}</strong> <span class="tag">${escapeHtml(p.note || "")}</span>${extra}</div><div>${hk(p.amount)}</div></div>`;
}

function sumOn(date) {
  return state.data.payments.reduce((acc, p) => acc + (p.date === date ? p.amount : 0), 0);
}

function optionText(opt, sheet) {
  const before = sheet.fundsNow;
  const after = opt.fundsAfter;
  const parts = [];
  if (sheet.category === "experience" || sheet.category === "development") {
    parts.push(`${FUND_NAME[sheet.category]} ${hk(before[sheet.category])} to ${hk(after[sheet.category])}`);
  }
  ["snack", "experience", "development", "savings"].forEach((fund) => {
    if ((opt.from[fund] || 0) > 0 && fund !== sheet.category) {
      parts.push(`${FUND_NAME[fund]} ${hk(before[fund])} to ${hk(after[fund])}`);
    }
  });
  let line = `${parts.join(". ")}.`;
  if (sheet.category === "main" || sheet.category === "snack") {
    line += opt.tomorrowAfter === sheet.tomorrow
      ? ` Tomorrow stays ${hk(sheet.tomorrow)}.`
      : ` Tomorrow goes from ${hk(sheet.tomorrow)} to ${hk(opt.tomorrowAfter)}.`;
  }
  return line;
}

function choiceLabel(choice) {
  if (choice === "snack") return "Take it from Snacks";
  if (choice === "borrow") return "Borrow from a flexible fund";
  return "Take it from Long-term Savings";
}

function sheetHtml(sheet) {
  const title = sheet.level >= 3
    ? "This comes out of Long-term Savings"
    : sheet.options.length > 1
      ? "Two ways to cover this"
      : sheet.level === 2
        ? "This borrows from a flexible fund"
        : "This comes out of Snacks";
  const intro = sheet.category === "main" || sheet.category === "snack"
    ? `This payment is bigger than the ${hk(sheet.todayRemaining)} left today.`
    : "This payment is bigger than the fund it came from.";
  const buttons = sheet.options.map((opt) => {
    const kind = opt.hole >= 3 ? "danger" : "primary";
    return `<p>${escapeHtml(optionText(opt, sheet))}</p><button class="${kind}" type="button" data-choice="${opt.choice}">${choiceLabel(opt.choice)}</button>`;
  }).join("");
  return `<div class="panel level-${sheet.level}"><h2>${title}</h2><p>${intro}</p><div class="stack">${buttons}<button class="ghost" id="dismiss" type="button">Cancel</button></div></div>`;
}

const PRICE_COLOR = {
  cheap: "#3cba54",
  normal: "#e2c200",
  expensive: "#e23b32",
  unknown: "#2f6fed",
};

function priceWords(price) {
  if (price === "cheap") return "Cheap";
  if (price === "normal") return "Normal";
  if (price === "expensive") return "Expensive";
  return "Price unknown";
}

function pinStyle(place, selected) {
  const fill = PRICE_COLOR[place.price] || PRICE_COLOR.unknown;
  return {
    radius: selected ? 9 : 6,
    color: selected ? "#172033" : fill,
    weight: selected ? 3 : 1,
    fillColor: fill,
    fillOpacity: 0.95,
  };
}

function mapFilters() {
  const kinds = [["food", "Food"], ["shop", "Shopping"]].map(([id, name]) =>
    `<button type="button" data-kind="${id}" class="${state.mapKind === id ? "on" : ""}">${name}</button>`
  ).join("");
  const radii = ["0.5", "1", "3", "5", "10"].map((km) =>
    `<button type="button" data-radius="${km}" class="${state.mapRadius === km ? "on" : ""}">${km} km</button>`
  ).join("");
  return `<div class="cats">${kinds}</div><div class="cats">${radii}</div>
    <div class="price-bar"></div>
    <div class="price-labels"><span>Cheap</span><span>Normal</span><span>Expensive</span></div>`;
}

function mapScreen() {
  const data = state.mapLoading ? null : state.map;
  const filters = mapFilters();
  if (!data) {
    const message = state.mapLoading
      ? "Loading places from OpenStreetMap."
      : (state.error || "Loading places from OpenStreetMap.");
    return `<div class="card"><div class="kicker">Around HKUST</div>${filters}<div class="explain">${escapeHtml(message)}</div><p class="explain">Blue means OpenStreetMap has no price. Green, yellow, and red appear only when the map data itself says cheap, normal, or expensive.</p></div>`;
  }
  const rows = data.places.length
    ? data.places.map((place) => {
      const price = PRICE_COLOR[place.price] ? place.price : "unknown";
      const on = place.id === state.selectedId ? " on" : "";
      return `<button type="button" class="place${on}" data-place="${escapeHtml(place.id)}"><span class="dot ${price}"></span><span><strong>${escapeHtml(place.name)}</strong><div class="tag">${escapeHtml(place.detail || "OpenStreetMap")} · ${place.distanceKm} km · ${priceWords(price)}</div></span></button>`;
    }).join("")
    : `<div class="explain">OpenStreetMap has no named ${data.kind === "food" ? "food places" : "shops"} inside ${data.radiusKm} km.</div>`;
  const count = data.total > data.shown
    ? `Showing the nearest ${data.shown} of ${data.total} named places.`
    : `${data.total} named places.`;
  return `<div class="card">
      <div class="kicker">Around ${escapeHtml(data.center.name)}</div>
      ${filters}
      <div id="osm-map"></div>
      <p class="explain">${count} Tap a place to show it on the map. Blue means the price is not in OpenStreetMap.</p>
    </div>
    <div class="list">${rows}</div>`;
}

let liveMap = null;
let markers = new Map();

function clearMap() {
  markers = new Map();
  if (!liveMap) return;
  liveMap.remove();
  liveMap = null;
}

function placeById(id) {
  return (state.map && state.map.places || []).find((place) => place.id === id);
}

function selectPlace(id) {
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

function mountMap() {
  const el = document.getElementById("osm-map");
  if (!el || !state.map || state.mapLoading || !window.L) return;
  const center = [state.map.center.lat, state.map.center.lng];
  const map = window.L.map(el, { zoomControl: true }).setView(center, 15);
  liveMap = map;
  window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(map);
  window.L.circle(center, {
    radius: state.map.radiusKm * 1000,
    color: "#1d4f91",
    weight: 1,
    fillOpacity: 0.06,
  }).addTo(map);
  const bounds = [center];
  state.map.places.forEach((place) => {
    bounds.push([place.lat, place.lng]);
    const marker = window.L.circleMarker([place.lat, place.lng], pinStyle(place, place.id === state.selectedId))
      .bindPopup(`<strong>${escapeHtml(place.name)}</strong><br>${escapeHtml(place.detail || "")}<br>${place.distanceKm} km<br>${priceWords(place.price)}`)
      .addTo(map);
    marker.on("click", () => selectPlace(place.id));
    markers.set(place.id, marker);
  });
  if (state.selectedId && markers.has(state.selectedId)) {
    const selected = placeById(state.selectedId);
    map.setView([selected.lat, selected.lng], 17);
    markers.get(state.selectedId).openPopup();
  } else if (bounds.length > 1) {
    map.fitBounds(bounds, { padding: [18, 18] });
  }
  setTimeout(() => map.invalidateSize(), 0);
}

const screens = { today: todayScreen, add: addScreen, week: weekScreen, day: dayScreen, settings: settingsScreen, map: mapScreen };

function bind() {
  document.getElementById("add")?.addEventListener("click", () => {
    state.draft = { amount: "", category: "main", note: "" };
    state.error = "";
    state.screen = "add";
    render();
    document.getElementById("amount")?.focus();
  });
  document.getElementById("go-settings")?.addEventListener("click", () => { state.screen = "settings"; render(); });
  document.getElementById("cancel-add")?.addEventListener("click", () => { state.screen = "today"; render(); });
  document.getElementById("back-week")?.addEventListener("click", () => { state.screen = "week"; render(); });
  document.querySelectorAll("[data-cat]").forEach((btn) => btn.addEventListener("click", () => {
    state.draft.category = btn.dataset.cat;
    state.draft.amount = document.getElementById("amount").value;
    state.draft.note = document.getElementById("note").value;
    render();
  }));
  document.getElementById("save")?.addEventListener("click", onSave);
  document.querySelectorAll("[data-day]").forEach((btn) => btn.addEventListener("click", () => {
    state.day = btn.dataset.day;
    state.screen = "day";
    render();
  }));
  document.querySelectorAll("[data-mode]").forEach((btn) => btn.addEventListener("click", async () => {
    try {
      const data = await api("/api/mode", { mode: btn.dataset.mode });
      applyState(data, { showNotice: false, error: "", screen: "today", sheet: null });
      render();
    } catch (err) {
      state.error = err.message;
      render();
    }
  }));
  document.getElementById("apply")?.addEventListener("click", applyNumbers);
  document.querySelectorAll("[data-kind]").forEach((btn) => btn.addEventListener("click", () => {
    state.mapKind = btn.dataset.kind;
    loadMap();
  }));
  document.querySelectorAll("[data-radius]").forEach((btn) => btn.addEventListener("click", () => {
    state.mapRadius = btn.dataset.radius;
    loadMap();
  }));
  document.querySelectorAll("[data-place]").forEach((btn) => btn.addEventListener("click", () => {
    selectPlace(btn.dataset.place);
  }));
  document.querySelectorAll("[data-choice]").forEach((btn) => btn.addEventListener("click", () => commit(state.sheet, btn.dataset.choice)));
  document.getElementById("dismiss")?.addEventListener("click", () => { state.sheet = null; render(); });
  mountMap();
}

async function onSave() {
  const raw = document.getElementById("amount").value;
  const note = document.getElementById("note").value.trim();
  const category = state.draft.category;
  state.draft = { amount: raw, category, note };
  if (parseAmount(raw) == null) {
    state.error = "Enter an amount greater than zero.";
    render();
    return;
  }
  try {
    const data = await api("/api/payments", { amount: raw, category, note });
    if (data.needsConfirm) {
      state.sheet = {
        level: data.level,
        options: data.options,
        fundsNow: data.state.view.fundsNow,
        tomorrow: data.state.view.tomorrow,
        todayRemaining: data.state.view.todayRemaining,
        category,
        amountRaw: raw,
        note,
      };
      state.data = data.state;
      state.view = data.state.view;
      render();
      return;
    }
    applyState(data.state, {
      showNotice: data.level === 1,
      sheet: null,
      screen: "today",
      error: "",
    });
    render();
  } catch (err) {
    state.error = err.message;
    render();
  }
}

async function commit(pending, choice) {
  try {
    const data = await api("/api/payments", {
      amount: pending.amountRaw,
      category: pending.category,
      note: pending.note,
      choice,
    });
    applyState(data.state, { showNotice: false, sheet: null, screen: "today", error: "" });
    render();
  } catch (err) {
    state.sheet = null;
    state.error = err.message;
    state.screen = "add";
    render();
  }
}

async function applyNumbers() {
  const body = {};
  for (const [id] of FUND_FIELDS) {
    body[id] = document.getElementById(id).value;
    if (parseAmount(body[id]) == null) {
      state.error = "Each fund needs a number greater than zero.";
      render();
      return;
    }
  }
  try {
    const data = await api("/api/settings", body);
    applyState(data, { error: "", screen: "today", showNotice: false });
    render();
  } catch (err) {
    state.error = err.message;
    render();
  }
}

document.getElementById("nav").addEventListener("click", (event) => {
  const btn = event.target.closest("button");
  if (!btn || !btn.dataset.screen) return;
  state.error = "";
  state.sheet = null;
  if (btn.dataset.screen === "map") loadMap();
  else {
    state.screen = btn.dataset.screen;
    state.mapLoading = false;
    render();
  }
});

let mapToken = 0;
async function loadMap() {
  const token = ++mapToken;
  state.screen = "map";
  state.mapLoading = true;
  state.error = "";
  state.selectedId = "";
  render();
  try {
    const data = await api(`/api/places?kind=${encodeURIComponent(state.mapKind)}&radius=${encodeURIComponent(state.mapRadius)}`);
    if (token !== mapToken) return;
    state.map = data;
    state.error = "";
  } catch (err) {
    if (token !== mapToken) return;
    state.map = null;
    state.error = err.message;
  }
  state.mapLoading = false;
  if (state.screen === "map") render();
}

api("/api/state").then((data) => {
  applyState(data);
  render();
}).catch(() => {
  document.getElementById("screen").innerHTML = `<div class="card"><div class="explain">The server is not running. Double-click run.bat in the SSUST-demo folder, then open http://127.0.0.1:8765.</div></div>`;
});
