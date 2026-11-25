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

// The text of the words, one line per visual row: a word joins a row when its centre, straightened by
// the tilt `slope`, is within `tolerance` x the usual word height of the row's centre. Rows go top to
// bottom, words left to right.
export function rebuildRows(words, slope = 0, tolerance = 0.5) {
  const items = (words || []).filter(usable).map((w) => {
    const cx = (w.x0 + w.x1) / 2;
    return { text: w.text.trim(), x0: w.x0, cy: (w.y0 + w.y1) / 2 - slope * cx, h: Math.max(1, w.y1 - w.y0) };
  });
  if (!items.length) return "";
  const heights = items.map((w) => w.h).sort((a, b) => a - b);
  const limit = tolerance * heights[Math.floor(heights.length / 2)];
  items.sort((a, b) => a.cy - b.cy);
  const rows = [];
  for (const item of items) {
    const row = rows[rows.length - 1];
    if (row && Math.abs(item.cy - row.cy) <= limit) {
      row.words.push(item);
      row.cy = row.words.reduce((s, w) => s + w.cy, 0) / row.words.length;
    } else {
      rows.push({ cy: item.cy, words: [item] });
    }
  }
  return rows.map((row) => row.words.sort((a, b) => a.x0 - b.x0).map((w) => w.text).join(" ")).join("\n");
}
