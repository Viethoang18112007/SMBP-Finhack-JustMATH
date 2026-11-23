// iPhone app, Settings: connect real Apple Pay payments and a home screen widget through the
// iOS Shortcuts app. Both call the SSUST server with this phone's id (X-SSUST-Device):
//   POST /api/shortcut/wallet  {"amount", "merchant", "card"}  -> Today > To review
//   GET  /api/shortcut/today   -> one line: what is left today, the streak, what waits for review
// The SSUST widget (WidgetKit, iOS 17+) reads GET /api/widget with the same phone code.
// Nothing is spent until the payment is confirmed in the app.

import { API_BASE, deviceId } from "../config.js";
import { escapeHtml } from "../format.js";

function copyRow(label, value) {
  return `<div class="copy-row"><span class="label">${escapeHtml(label)}</span>`
    + `<code class="copy-value">${escapeHtml(value)}</code>`
    + `<button type="button" class="ghost small" data-copy="${escapeHtml(value)}">Copy</button></div>`;
}

export function shortcutsCard() {
  const wallet = `${API_BASE}/api/shortcut/wallet`;
  const today = `${API_BASE}/api/shortcut/today`;
  return `<details class="card fold" id="shortcuts-card">
      <summary><span class="title">Apple Pay and widget</span></summary>
      <p class="sub">Uses the Shortcuts app on this iPhone. Paste these values when the steps ask for them.</p>
      ${copyRow("Header name", "X-SSUST-Device")}
      ${copyRow("Header value (this phone)", deviceId())}
      <h3 class="guide-title">Add Apple Pay payments automatically</h3>
      ${copyRow("URL", wallet)}
      <ol class="guide">
        <li>Open <strong>Shortcuts</strong>, tab <strong>Automation</strong>, then <strong>+</strong> and <strong>Wallet</strong>.</li>
        <li>Pick your cards, choose <strong>Run Immediately</strong>, then <strong>New Blank Automation</strong>.</li>
        <li>Add the action <strong>Get Contents of URL</strong> and paste the URL above.</li>
        <li>Tap the arrow: Method <strong>POST</strong>, add the header above, Request Body <strong>JSON</strong>.</li>
        <li>Add three text fields: <code>amount</code> = Shortcut Input &gt; Amount, <code>merchant</code> = Merchant, <code>card</code> = Card or Pass.</li>
        <li>Pay with Apple Pay: the payment shows in Today under <strong>To review</strong>. Pick the fund and confirm.</li>
      </ol>
      <h3 class="guide-title">SSUST widget on the home screen</h3>
      <ol class="guide">
        <li>Hold an empty spot on the home screen, <strong>Edit</strong>, <strong>Add Widget</strong>, then <strong>SSUST</strong>.</li>
        <li>Hold the new widget, <strong>Edit Widget</strong>, and paste the header value above as <strong>Phone code</strong>.</li>
        <li>It shows what is left today, your streak and what waits for review. It updates about every 30 minutes.</li>
      </ol>
      <h3 class="guide-title">Shortcuts widget (iOS 16 and older)</h3>
      ${copyRow("URL", today)}
      <ol class="guide">
        <li>In <strong>Shortcuts</strong>, tap <strong>+</strong> and name it "SSUST today".</li>
        <li>Add <strong>Get Contents of URL</strong> with the URL above and the same header (Method GET).</li>
        <li>Add <strong>Show Notification</strong> with Contents of URL.</li>
        <li>On the home screen, hold an empty spot, <strong>Edit</strong>, <strong>Add Widget</strong>, <strong>Shortcuts</strong>, pick "SSUST today". A tap on it shows what is left today.</li>
      </ol>
      <p class="hint">Keep the header value private: it opens this phone's SSUST data.</p>
    </details>`;
}
