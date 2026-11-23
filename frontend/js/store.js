// The single UI state object and read helpers over the server state.

const FUND_VIEW_KEY = "ssust.fundView";

// The funds card shows a list (the default) or tanks. Storage may be missing or blocked.
export function readFundView() {
  try {
    return window.localStorage.getItem(FUND_VIEW_KEY) === "tanks" ? "tanks" : "list";
  } catch (err) {
    return "list";
  }
}

const PHONE_VIEW_KEY = "ssust.phoneView";

// Desktop shows the app inside a phone frame unless the person turned it off.
export function readPhoneView() {
  try {
    return window.localStorage.getItem(PHONE_VIEW_KEY) !== "off";
  } catch (err) {
    return true;
  }
}

export function setPhoneView(on) {
  state.phoneView = Boolean(on);
  try {
    window.localStorage.setItem(PHONE_VIEW_KEY, state.phoneView ? "on" : "off");
  } catch (err) {
    // the choice lasts until the page is reloaded
  }
}

export const state = {
  data: null, // the current week, always: every write goes here
  view: null,
  past: null, // a previous week shown read-only on the Week and Day screens, or null
  screen: "today",
  day: null,
  draft: { amount: "", category: "main", note: "" },
  error: "",
  errorField: null, // the Settings field the error is about, or null
  fundDraft: null, // what was typed in Settings, kept when the server refuses it
  sheet: null, // the reallocation step of the Add sheet, or null
  adding: false, // the Add payment sheet is open (over the current screen)
  toast: null, // { text, undoId, confirming }: the short message above the Add button
  undoId: null, // the payment whose "Yes, undo" step is showing
  flash: "", // a one-time confirmation, shown as a toast (e.g. after an undo)
  saving: false, // a payment request is in flight: Save and the cover buttons are disabled
  attempt: null, // { key, requestId }: reused when the same amount and category are submitted again
  showNotice: false,
  mapKind: "food",
  mapRadius: "3",
  mapFitsOnly: false, // the "Fits today's HK$X" toggle on the map
  map: null,
  mapLoading: false,
  selectedId: "",
  fundView: readFundView(), // "list" or "tanks", a per-browser preference kept across modes
  tankFlow: null, // { category, from }: the payment just saved, so the tanks can show where money went
  scan: null, // the receipt scan in the Add sheet: { status, percent, words, line, merchant }
  phoneView: readPhoneView(), // the phone frame on wide screens
  deviceView: "home", // inside the frame: "home" (home screen) or "app"
  // The Feedback tab: the stars and words being written, and the latest feedback (null: loading).
  feedback: { rating: 0, text: "", list: null, sending: false, sent: false, error: "" },
};

export function setFundView(view) {
  state.fundView = view === "tanks" ? "tanks" : "list";
  try {
    window.localStorage.setItem(FUND_VIEW_KEY, state.fundView);
  } catch (err) {
    // the choice simply lasts until the page is reloaded
  }
}

export function applyState(payload, extra) {
  state.data = payload;
  state.view = payload.view;
  state.updatedAt = new Date(); // shown on the home screen widgets
  if (extra) Object.assign(state, extra);
}

// The week shown on the Week and Day screens: a past week, or the current one.
export function shownWeek() {
  return state.past || state.data;
}

export function paymentsOn(date, week = state.data) {
  return week.payments.filter((p) => p.date === date);
}

export function sumOn(date, week = state.data) {
  return week.payments.reduce((acc, p) => acc + (p.date === date ? p.amount : 0), 0);
}
