// Receipt rows rebuilt from OCR word boxes. Pure functions: no DOM, no globals, no imports, so a
// native scanner can reuse them. A word is { text, x0, y0, x1, y1 } in pixels, every pass in the
// same frame (the trimmed receipt picture). A label read in one pass ("Amount") and its price read
// in another pass ("$1,032.0") end up on one line: "Amount $1,032.0".

const MAX_SLOPE = 0.15; // a receipt tilted more than about 8.5 degrees is not straightened
const MIN_BASELINE = 40; // pixels: shorter baselines say little about the tilt
const MONEY = /\d[.,]\d{1,2}\s*$/;

function usable(word) {
  return word && typeof word.text === "string" && word.text.trim() !== ""
    && [word.x0, word.y0, word.x1, word.y1].every(Number.isFinite) && word.x1 >= word.x0 && word.y1 >= word.y0;
}

// The receipt's tilt (dy per dx) from text baselines [{ x0, y0, x1, y1 }]: their median slope, 0 if unknown.
export function skewOf(baselines) {
  const slopes = (baselines || [])
    .filter((b) => b && [b.x0, b.y0, b.x1, b.y1].every(Number.isFinite) && b.x1 - b.x0 >= MIN_BASELINE)
    .map((b) => (b.y1 - b.y0) / (b.x1 - b.x0))
    .sort((a, b) => a - b);
  if (!slopes.length) return 0;
  const mid = slopes[Math.floor(slopes.length / 2)];
  return Math.max(-MAX_SLOPE, Math.min(MAX_SLOPE, mid));
}

// Words moved by (dx, dy): a pass on a cropped part of the picture back into the whole picture's frame.
export function shiftWords(words, dx, dy = 0) {
  return (words || []).filter(usable).map((w) => ({ ...w, x0: w.x0 + dx, x1: w.x1 + dx, y0: w.y0 + dy, y1: w.y1 + dy }));
}

function overlap(a, b) {
  const w = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0);
  const h = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
  if (w <= 0 || h <= 0) return 0;
  const smaller = Math.min((a.x1 - a.x0) * (a.y1 - a.y0), (b.x1 - b.x0) * (b.y1 - b.y0)) || 1;
  return (w * h) / smaller;
}

// The words of `base` plus those of `extra` that were not already read at the same place. Where both
// passes read the same spot, the base word is kept, unless only the extra word reads as a price
// (a digits-only pass reads "$1,032.0" where the first pass read "S1,O32.O").
export function mergeWords(base, extra) {
  const out = (base || []).filter(usable).map((w) => ({ ...w }));
  for (const word of (extra || []).filter(usable)) {
    const i = out.findIndex((w) => overlap(w, word) > 0.5);
    if (i < 0) out.push({ ...word });
    else if (MONEY.test(word.text) && !MONEY.test(out[i].text) && /\d/.test(out[i].text)) out[i] = { ...word };
  }
  return out;
}

// How far apart (centres, straightened) two words can be, as a share of the larger of their two
// heights: within JOIN they share a row; a row never holds two words further apart than APART.
const JOIN = 0.6;
const APART = 1.0;

// Visual rows, top to bottom: [{ words, top, bottom }], each word { text, x0, cy, h, top, bottom }.
// Each pair of words is judged by its own heights (a big printed "Amount" and its bigger price are one
// row even when their centres differ by most of a normal line). Pairs are joined closest first, and two
// rows never join if any of their words would end up more than APART apart, so a big price is never
// pulled into the row above it.
function groupRows(words, slope, join) {
  const items = (words || []).filter(usable).map((w) => {
    const shift = slope * ((w.x0 + w.x1) / 2);
    return { text: w.text.trim(), x0: w.x0, cy: (w.y0 + w.y1) / 2 - shift, h: Math.max(1, w.y1 - w.y0),
      top: w.y0 - shift, bottom: w.y1 - shift };
  });
  const gap = (a, b) => Math.abs(a.cy - b.cy) / Math.max(a.h, b.h);
  const pairs = [];
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      const g = gap(items[i], items[j]);
      if (g <= join) pairs.push([g, i, j]);
    }
  }
  pairs.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  const rowOf = items.map((_, i) => [i]);
  for (const [, i, j] of pairs) {
    const a = rowOf[i];
    const b = rowOf[j];
    if (a === b || a.some((p) => b.some((q) => gap(items[p], items[q]) > APART))) continue;
    for (const k of b) {
      a.push(k);
      rowOf[k] = a;
    }
  }
  return [...new Set(rowOf)]
    .map((row) => {
      const ws = row.map((k) => items[k]).sort((a, b) => a.x0 - b.x0);
      return { words: ws, cy: ws.reduce((s, w) => s + w.cy, 0) / ws.length,
        top: Math.min(...ws.map((w) => w.top)), bottom: Math.max(...ws.map((w) => w.bottom)) };
    })
    .sort((a, b) => a.cy - b.cy);
}

const rowText = (row) => row.words.map((w) => w.text).join(" ");

// The text of the words, one line per visual row: two words share a row when their centres, straightened
// by the tilt `slope`, are within `tolerance` x the larger of their two heights. Rows go top to bottom,
// words left to right.
export function rebuildRows(words, slope = 0, tolerance = JOIN) {
  return groupRows(words, slope, tolerance).map(rowText).join("\n");
}

// Lines read by the iPhone's own text recognition ({ text, x, y, w, h }, the box from 0 to 1, from the
// top left) as words in a `size` x `size` frame, the shape rebuildRows works on.
export function wordsFromLines(lines, size = 1000) {
  return (lines || [])
    .filter((l) => l && typeof l.text === "string" && [l.x, l.y, l.w, l.h].every(Number.isFinite))
    .map((l) => ({ text: l.text, x0: l.x * size, y0: l.y * size, x1: (l.x + l.w) * size, y1: (l.y + l.h) * size }))
    .filter(usable);
}

// A row that is only a price ("$1,032.0", "HK$ 38", "-$0.80"), a row with an amount in it, and the
// total labels the server looks for (receipt.py). A total label left without a price on its own row is
// marked with NO_PRICE, so "What the phone read" shows where the rows could not be paired.
const PRICE_ONLY = /^\s*-?\s*(?:HK\s?\$|HKD|\$)?\s*-?\s*\d[\d,]*(?:\s?[.,]\s?\d{1,2})?\s*(?:\$HK|HKD)?\s*$/i;
const HAS_AMOUNT = /\d\s?[.,]\s?\d{1,2}(?!\d)|(?:\$|HKD)\s*\d|\d\s*(?:\$HK|HKD)|\d\s*$/i;
const TOTAL_LABEL = /\b(?:sub ?-?total|total|amount|amt|payable|due|service)\b|小計|小计|合計|合计|總計|总计|總數|總額|总额|應付|应付|金額|金额/i;
export const NO_PRICE = "(no price on this row)";

const overlapOf = (a, b) => Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);

// A price-only row joins a row beside it that has no amount when their boxes overlap vertically: the
// same printed line, read as two pieces a little more than JOIN apart.
function pairPrices(rows) {
  const out = rows.map((row) => ({ ...row, words: [...row.words] }));
  for (let i = 0; i < out.length; i += 1) {
    const price = out[i];
    if (!price || !PRICE_ONLY.test(rowText(price))) continue;
    const near = [out[i - 1], out[i + 1]]
      .filter((row) => row && !HAS_AMOUNT.test(rowText(row)) && overlapOf(row, price) > 0)
      .sort((a, b) => overlapOf(b, price) - overlapOf(a, price));
    if (!near.length) continue;
    const label = near[0];
    label.words = [...label.words, ...price.words].sort((a, b) => a.x0 - b.x0);
    label.top = Math.min(label.top, price.top);
    label.bottom = Math.max(label.bottom, price.bottom);
    out[i] = null;
  }
  return out.filter(Boolean);
}

// The text of scanned pages (each a list of lines as above), one visual row per line, so a label and
// its amount read as two pieces ("Amount", "$1,032.0") end up on one line, even when the amount is
// printed bigger. The phone's scan screen already straightens the page, so no tilt is applied.
export function textOfPages(pages) {
  return (Array.isArray(pages) ? pages : [])
    .map((lines) => pairPrices(groupRows(wordsFromLines(lines), 0, JOIN))
      .map((row) => {
        const text = rowText(row);
        return TOTAL_LABEL.test(text) && !HAS_AMOUNT.test(text) ? `${text} ${NO_PRICE}` : text;
      })
      .join("\n"))
    .filter(Boolean)
    .join("\n");
}
