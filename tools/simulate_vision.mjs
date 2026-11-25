// Feeds simulated iPhone text recognition output through the app's own row rebuilding
// (frontend/js/rows.js textOfPages) and then the server's total finder (backend receipt.py
// parse_receipt, through tools/parse_receipt_text.py). Run by hand (Node 18 or later, Python 3):
//   node tools/simulate_vision.mjs            the table
//   node tools/simulate_vision.mjs --text     the table and each rebuilt text
// Exit code 1 if a layout picks the wrong amount.
//
// A line is { text, confidence, x, y, w, h }: the box from 0 to 1, from the top left, as
// ios/App/App/ReceiptScanner.swift returns it. Layouts:
//   i     one line per printed row ("Amount $1,032.0")
//   ii    label and price read apart on the same row, the price a third of a line higher or lower
//   iii   the Amount row printed bigger, its label and price centres 0.4 to 0.8 of a normal line apart
//   iv    read column by column: every label first, then every price (real boxes)
//   iv-t  the same lines as plain text in reading order, rows never rebuilt (the parser alone): text
//         cannot say which price goes with which label, so a best guess is fine, a sure wrong total is not

import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const source = readFileSync(new URL("../frontend/js/rows.js", import.meta.url), "utf8");
const R = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));

const H = 0.012; // a normal printed line, as a share of the page height
const PITCH = 0.022; // from one row's centre to the next
const LX = 0.06; // labels start here
const PX = 0.70; // prices start here

// [label, price, big]: a row of the receipt, top to bottom. A row without a price is text only.
const RECEIPTS = {
  "Cafe Boheme": {
    want: 103200,
    rows: [
      ["Cafe Boheme"], ["Phone: +852 9251 6870"], ["Order Time: 2026-11-22 12:21:16"],
      ["Receipt No.: 20261122122116E7"], ["Number of Patron: 5"],
      ["1 Apple Juice", "$38.0"], ["1 Aqua Panna 750ML", "$68.0"], ["1 Truffle & Camembert Pizza", "$178.0"],
      ["1 BBQ Pork Rib 1KG", "$388.0"], ["1 Seafood Linguine", "$178.0"], ["1 Marshmallow Banana Pizza", "$88.0"],
      ["Subtotal", "$938.0"], ["Service Charge(10%)", "$93.8"], ["Amount", "$1,032.0", true], ["Thank You"],
    ],
  },
  Fusion: {
    want: 1510,
    rows: [
      ["fusion"], ["HKUST"], ["124715 能量果凍-白葡萄味 1", "$15.90"], ["5% OFF (SU-SCO)", "-$0.80"],
      ["1 小計", "$15.10"], ["MASTER", "$15.10"], ["找續", "$0.00"], ["GP.MASTERCARD", "$15.10"],
      ["APP Label:DEBIT MASTERCARD"], ["25/11/26 15:25:28"],
    ],
  },
};

const width = (text) => Math.min(0.6, text.length * 0.012);
const line = (text, x, cy, h) => ({ text, confidence: 0.9, x, y: cy - h / 2, w: width(text), h });

// Row centres, a big row getting more room.
function centres(rows, bigScale) {
  const out = [];
  let cy = 0.05;
  rows.forEach(([, , big], i) => {
    if (i) cy += big || rows[i - 1][2] ? PITCH * (1 + bigScale) / 2 + PITCH / 2 : PITCH;
    out.push(cy);
  });
  return out;
}

// One layout as [label lines, price lines] in reading order.
function build(rows, kind, offset = 0.6) {
  const big = kind === "iii" ? 2 : 1;
  const cys = centres(rows, big);
  const labels = [];
  const prices = [];
  rows.forEach(([label, price, isBig], i) => {
    const cy = cys[i];
    if (kind === "i") {
      const h = isBig ? H * 2 : H;
      const text = price ? `${label} ${price}` : label;
      labels.push({ ...line(text, LX, cy, h), w: price ? PX + width(price) - LX : width(text) });
      return;
    }
    if (kind === "iii" && isBig) {
      // The label a bit smaller than the price, their centres `offset` normal lines apart.
      labels.push(line(label, LX, cy, H * 1.5));
      if (price) prices.push(line(price, PX, cy + offset * H, H * 2));
      return;
    }
    labels.push(line(label, LX, cy, H));
    if (price) prices.push(line(price, PX, cy + (i % 2 ? 1 : -1) * H / 3, H));
  });
  return [labels, prices];
}

// Each layout: { name, receipt, text } where text is what the server receives.
function layouts() {
  const out = [];
  for (const [name, receipt] of Object.entries(RECEIPTS)) {
    const add = (layout, text) => out.push({ layout, receipt: name, want: receipt.want, text });
    const page = (labels, prices, interleave) => {
      if (!interleave) return [[...labels, ...prices]];
      // Row by row, the way a reader goes along each line.
      return [[...labels, ...prices].sort((a, b) => a.y + a.h / 2 - (b.y + b.h / 2) || a.x - b.x)];
    };
    const [l1] = build(receipt.rows, "i");
    add("i", R.textOfPages([l1]));
    const [l2, p2] = build(receipt.rows, "ii");
    add("ii", R.textOfPages(page(l2, p2, true)));
    for (const offset of [0.4, 0.6, 0.8, -0.4, -0.6, -0.8]) {
      const [l3, p3] = build(receipt.rows, "iii", offset);
      add(`iii ${offset > 0 ? "+" : ""}${offset}`, R.textOfPages(page(l3, p3, true)));
    }
    const [l4, p4] = build(receipt.rows, "ii");
    add("iv", R.textOfPages(page(l4, p4, false)));
    add("iv-t", [...l4, ...p4].map((l) => l.text).join("\n"));
    const [l5, p5] = build(receipt.rows, "iii", 0.6);
    add("iv big", R.textOfPages(page(l5, p5, false)));
  }
  return out;
}

const runs = layouts();
const python = process.platform === "win32" ? "python" : "python3";
const helper = fileURLToPath(new URL("./parse_receipt_text.py", import.meta.url));
const done = spawnSync(python, [helper], { input: JSON.stringify(runs.map((r) => r.text)), encoding: "utf8" });
if (done.status !== 0) {
  console.error(done.stderr || done.error);
  process.exit(2);
}
const results = JSON.parse(done.stdout);

const money = (cents) => (Number.isInteger(cents) ? (cents / 100).toFixed(2) : "none");
const showText = process.argv.includes("--text");
let wrong = 0;
console.log("layout     receipt       chosen     right?  line used");
runs.forEach((run, i) => {
  const r = results[i];
  const right = r.found && r.amount === run.want && !r.guess;
  const textOnly = run.layout === "iv-t";
  const verdict = right ? "right" : textOnly && (r.guess || !r.found) ? "guess" : "WRONG";
  if (verdict === "WRONG") wrong += 1;
  console.log(`${run.layout.padEnd(10)} ${run.receipt.padEnd(13)} ${money(r.amount).padStart(8)}   ${verdict.padEnd(6)}  ${r.line || "-"}`);
  if (showText) console.log("   " + run.text.split("\n").join("\n   ") + "\n");
});
console.log(wrong ? `${wrong} layout(s) wrong` : "all layouts right");
process.exit(wrong ? 1 : 0);
