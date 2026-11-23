// iPhone app: hand this phone's SSUST id to the home screen widget, through the native
// AppViewController ("ssustWidget" message) and the App Group it shares with the widget, and ask the
// widget to refresh when today's numbers change. On the web, or without the native channel, nothing.

import { NATIVE, deviceId } from "./config.js";
import { state } from "./store.js";

let last = "";

// True when the native channel to the widget exists (an app build with AppViewController).
export function widgetLinked() {
  try {
    return Boolean(NATIVE && window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.ssustWidget);
  } catch (error) {
    return false;
  }
}

export function syncWidget() {
  if (!NATIVE) return;
  let channel = null;
  try {
    channel = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.ssustWidget;
  } catch (error) {
    return;
  }
  if (!channel) return;
  const data = state.data;
  const view = data && data.view;
  const key = view
    ? [data.weekStart, view.todayRemaining, view.spentToday, (data.payments || []).length, (data.inbox || []).length].join("|")
    : "none";
  if (key === last) return;
  last = key;
  try {
    channel.postMessage({ device: deviceId() });
  } catch (error) {
    // The widget still refreshes on its own every 30 minutes.
  }
}
