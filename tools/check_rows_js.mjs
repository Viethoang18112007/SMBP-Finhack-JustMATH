// Checks the pure row rebuilding in frontend/js/rows.js (receipts read on the phone or offline).
// Run by hand (Node 18 or later):
//   node tools/check_rows_js.mjs
// The module is loaded from its text, so it works whatever package.json says about modules.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../frontend/js/rows.js", import.meta.url), "utf8");
const R = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));

for (const name of ["skewOf", "shiftWords", "mergeWords", "rebuildRows", "wordsFromLines", "textOfPages"]) {
  assert.equal(typeof R[name], "function", name);
}

// Phone lines: { text, x, y, w, h } from 0 to 1, from the top left; `cy` is the centre.
const H = 0.012;
const at = (text, x, cy, h = H, w = 0.2) => ({ text, confidence: 0.9, x, y: cy - h / 2, w, h });
const rowsOf = (lines) => R.textOfPages([lines]).split("\n");

// (ii) label and price read apart, the price a third of a line higher or lower.
{
  const lines = [
    at("Subtotal", 0.06, 0.50), at("$938.0", 0.7, 0.50 + H / 3, H, 0.1),
    at("Service Charge(10%)", 0.06, 0.522), at("$93.8", 0.7, 0.522 - H / 3, H, 0.1),
    at("Amount", 0.06, 0.544), at("$1,032.0", 0.7, 0.544 + H / 3, H, 0.1),
  ];
  assert.deepEqual(rowsOf(lines), ["Subtotal $938.0", "Service Charge(10%) $93.8", "Amount $1,032.0"]);
}

// (iii) the Amount row printed bigger, label and price centres 0.4 to 0.8 of a normal line apart,
// the price above or below. Never mixed with the service charge row just above.
for (const offset of [0.4, 0.6, 0.8, -0.4, -0.6, -0.8]) {
  const lines = [
    at("Subtotal", 0.06, 0.50), at("$938.0", 0.7, 0.50, H, 0.1),
    at("Service Charge(10%)", 0.06, 0.522), at("$93.8", 0.7, 0.522, H, 0.1),
    at("Amount", 0.06, 0.566, H * 1.5), at("$1,032.0", 0.66, 0.566 + offset * H, H * 2, 0.16),
    at("Thank You", 0.3, 0.61),
  ];
  assert.deepEqual(rowsOf(lines),
    ["Subtotal $938.0", "Service Charge(10%) $93.8", "Amount $1,032.0", "Thank You"], `offset ${offset}`);
}

// (iii) same height, centres 0.8 of a line apart: the boxes still overlap, so one row.
assert.deepEqual(rowsOf([at("Amount", 0.06, 0.5), at("$1,032.0", 0.7, 0.5 + 0.8 * H, H, 0.1)]), ["Amount $1,032.0"]);

// (iv) read column by column: every label first, then every price, with their real boxes.
{
  const labels = ["Subtotal", "Service Charge(10%)", "Amount"].map((t, i) => at(t, 0.06, 0.5 + i * 0.022));
  const prices = ["$938.0", "$93.8", "$1,032.0"].map((t, i) => at(t, 0.7, 0.5 + i * 0.022 + (i % 2 ? 1 : -1) * H / 4, H, 0.1));
  assert.deepEqual(rowsOf([...labels, ...prices]), ["Subtotal $938.0", "Service Charge(10%) $93.8", "Amount $1,032.0"]);
  assert.deepEqual(rowsOf([...prices, ...labels]), ["Subtotal $938.0", "Service Charge(10%) $93.8", "Amount $1,032.0"]);
}

// Normal rows close together stay apart; a big row never swallows its neighbours.
{
  const lines = [at("Apple Juice $38.0", 0.06, 0.5), at("Aqua Panna $68.0", 0.06, 0.5 + 1.4 * H),
    at("AMOUNT", 0.06, 0.5 + 3.2 * H, H * 2), at("Thank You", 0.06, 0.5 + 4.8 * H)];
  assert.deepEqual(rowsOf(lines), ["Apple Juice $38.0", "Aqua Panna $68.0", "AMOUNT (no price on this row)", "Thank You"]);
}

// A total label with no price on its own row is marked, the price on the next row stays on its own line.
{
  const lines = [at("TOTAL", 0.06, 0.5), at("$48.00", 0.7, 0.5 + 1.6 * H, H, 0.1), at("Thanks", 0.06, 0.5 + 3.2 * H)];
  assert.deepEqual(rowsOf(lines), ["TOTAL (no price on this row)", "$48.00", "Thanks"]);
  // Labels with a price, and lines that are not total labels, are never marked.
  assert.deepEqual(rowsOf([at("Total 48.00", 0.06, 0.5), at("Cafe Boheme", 0.06, 0.6)]), ["Total 48.00", "Cafe Boheme"]);
  assert.deepEqual(rowsOf([at("小計", 0.06, 0.5), at("$15.10", 0.7, 0.5, H, 0.1)]), ["小計 $15.10"]);
  assert.deepEqual(rowsOf([at("小計", 0.06, 0.5)]), ["小計 (no price on this row)"]);
}

// rebuildRows (pixels, the offline reader): two words share a row by their own heights.
{
  const word = (text, x0, cy, h, w = 60) => ({ text, x0, x1: x0 + w, y0: cy - h / 2, y1: cy + h / 2 });
  const words = [word("Apple", 10, 100, 20), word("$38.0", 300, 100, 20), word("Pizza", 10, 130, 20), word("$88.0", 300, 130, 20),
    word("Amount", 10, 170, 30), word("$1,032.0", 280, 170 - 16, 40, 100), word("Thanks", 10, 210, 20)];
  assert.equal(R.rebuildRows(words), "Apple $38.0\nPizza $88.0\nAmount $1,032.0\nThanks");
  // The marks are only for the phone's lines: rebuildRows adds nothing.
  assert.equal(R.rebuildRows([word("TOTAL", 10, 100, 20), word("$48.00", 300, 140, 20)]), "TOTAL\n$48.00");
  // Tilted rows, straightened by the slope.
  const tilted = [word("Coffee", 10, 100, 20), word("$22.50", 400, 100 + 0.05 * 420, 20), word("Total", 10, 140, 20),
    word("$62.50", 400, 140 + 0.05 * 420, 20)];
  assert.equal(R.rebuildRows(tilted, 0.05), "Coffee $22.50\nTotal $62.50");
  assert.equal(R.rebuildRows([]), "");
  assert.equal(R.rebuildRows(null), "");
}

// Several pages, and bad input.
assert.equal(R.textOfPages([[at("Shop", 0.1, 0.1)], [at("TOTAL $5.00", 0.1, 0.1)]]), "Shop\nTOTAL $5.00");
assert.equal(R.textOfPages(null), "");
assert.equal(R.textOfPages([[{ text: "x" }], []]), "");

console.log("all rows checks passed");
