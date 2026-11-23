// iPhone app, Settings: connect real Apple Pay payments through the iOS Shortcuts app, and the
// home screen widget. Both use this phone's id (X-SSUST-Device):
//   POST /api/shortcut/wallet  {"amount", "merchant", "card"}  -> Today > To review
//   GET  /api/widget           -> the SSUST widget (WidgetKit); the app hands it the id itself
//   GET  /api/shortcut/today   -> one line, for a Shortcuts widget on iOS 16 and older
// Nothing is spent until the payment is confirmed in the app. "walletLast" is the last message the
// automation sent (accepted or not), so a setup can be checked right after a payment.

import { API_BASE, deviceId } from "../config.js";
import { escapeHtml } from "../format.js";
import { state } from "../store.js";

function copyRow(label, value) {
  return `<div class="copy-row"><span class="label">${escapeHtml(label)}</span>`
    + `<code class="copy-value">${escapeHtml(value)}</code>`
    + `<button type="button" class="ghost small" data-copy="${escapeHtml(value)}">Copy</button></div>`;
}

function lastMessage() {
  const last = state.data && state.data.walletLast;
  if (!last) {
    return `<p class="hint">Nothing received from Apple Pay yet. After a payment, it shows here.</p>`;
  }
  const when = new Date(last.at);
  const time = Number.isNaN(when.getTime())
    ? ""
    : when.toLocaleString("en-GB", { timeZone: "Asia/Hong_Kong", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const what = last.ok
    ? `Received ${escapeHtml(last.detail)}. It waits in Today under To review.`
    : `Refused: ${escapeHtml(last.detail)} It sent "${escapeHtml(last.amount)}".`;
  return `<p class="notice ${last.ok ? "" : "warn"}" role="status">Last Apple Pay message, ${escapeHtml(time)}: ${what}</p>`;
}

export function shortcutsCard() {
  const wallet = `${API_BASE}/api/shortcut/wallet`;
  const today = `${API_BASE}/api/shortcut/today`;
  return `<section class="card" id="shortcuts-card" aria-labelledby="shortcuts-title">
      <h2 class="title" id="shortcuts-title">Apple Pay</h2>
      <p class="sub">Each Apple Pay payment lands in Today under To review. Set it up once in the Shortcuts app (Raccourcis).</p>
      ${lastMessage()}
      <details class="fold">
        <summary><span class="label">How to set it up</span></summary>
        ${copyRow("URL", wallet)}
        ${copyRow("Header name", "X-SSUST-Device")}
        ${copyRow("Header value (this phone)", deviceId())}
        <ol class="guide">
          <li>Open <strong>Shortcuts</strong> (Raccourcis), tab <strong>Automation</strong>, then <strong>+</strong> and <strong>Wallet</strong> (Cartes et cartes de transport).</li>
          <li>Pick your cards, choose <strong>Run Immediately</strong> (Exécuter immédiatement), then <strong>New Blank Automation</strong>.</li>
          <li>Add the action <strong>Get Contents of URL</strong> (Obtenir le contenu de l'URL) and paste the URL.</li>
          <li>Tap the arrow: Method <strong>POST</strong>, add the header (name and value above), Request Body <strong>JSON</strong>.</li>
          <li>Add three text fields: <code>amount</code> = Shortcut Input &gt; <strong>Amount</strong> (Montant), <code>merchant</code> = <strong>Merchant</strong> (Commerçant), <code>card</code> = <strong>Card or Pass</strong>.</li>
          <li>Pay with Apple Pay, then open SSUST: the line above says what arrived.</li>
        </ol>
        <p class="hint">Octopus in Wallet: transit taps may not start the automation. Keep the header value private.</p>
      </details>
    </section>
    <section class="card" aria-labelledby="widget-title">
      <h2 class="title" id="widget-title">SSUST widget</h2>
      <p class="sub">Hold an empty spot on the home screen, Edit, Add Widget, then SSUST. Small, medium, large and lock screen sizes. It updates when you use the app and about every 30 minutes.</p>
      <details class="fold">
        <summary><span class="label">iOS 16 or older</span></summary>
        ${copyRow("URL", today)}
        <ol class="guide">
          <li>In <strong>Shortcuts</strong>, make a shortcut "SSUST today" with <strong>Get Contents of URL</strong> (the URL above, Method GET, the same header), then <strong>Show Notification</strong>.</li>
          <li>Add the <strong>Shortcuts</strong> widget and pick "SSUST today".</li>
        </ol>
      </details>
    </section>`;
}
