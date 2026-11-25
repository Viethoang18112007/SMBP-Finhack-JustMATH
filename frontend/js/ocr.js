// "Scan receipt": offline OCR in the browser with the vendored tesseract.js, loaded only when
// the button is used. The text read is sent to the server (POST /api/receipt/parse), which
// finds the total with tested rules. Nothing is saved here: the Add form is only pre-filled.

import { mergeWords, rebuildRows, shiftWords, skewOf } from "./rows.js";

const BASE = new URL("../vendor/tesseract/", import.meta.url);
const MAX_BYTES = 3800; // the server accepts 4 KB request bodies
const MAX_CHARS = 3500; // and at most this much text (receipt.MAX_TEXT)

let scriptPromise = null;

function loadScript() {
  if (window.Tesseract) return Promise.resolve();
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = new URL("tesseract.min.js", BASE).href;
      script.onload = () => resolve();
      script.onerror = () => {
        scriptPromise = null;
        reject(new Error("The offline reader could not load."));
      };
      document.head.appendChild(script);
    });
  }
  return scriptPromise;
}

const LONG_SIDE = 2000; // pixels on the longer side of the receipt: small print stays readable, a phone stays fast
const MAX_UPSCALE = 3; // a small picture (a screenshot, a far receipt) is enlarged up to 3x
const PROBE_SIDE = 400; // the dark border is found on a small copy
const DARK = 40; // a row or column darker than this on average is border, not receipt
const LIGHT = 225; // a row or column lighter than this on average, and flat, is a white border
const FLAT = 12; // standard deviation under which a light row or column holds no print
const MIN_KEEP = 0.25; // a crop keeping less than this of a side is ignored (a dark photo, not a border)

// An upright picture of the file: an <img> applies the photo's EXIF rotation (an iPhone stores
// portrait photos sideways). The web page's CSP blocks blob: images, so there createImageBitmap is used.
function loadPicture(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("no image")); };
    img.src = url;
  }).catch(() => createImageBitmap(file));
}

function toGrey(px, count) {
  const grey = new Uint8ClampedArray(count);
  for (let i = 0; i < count; i += 1) grey[i] = (px[i * 4] * 299 + px[i * 4 + 1] * 587 + px[i * 4 + 2] * 114) / 1000;
  return grey;
}

// The receipt's part of the picture: rows and columns at the edges that are almost black (the bars
// around a screenshot, a dark table) or flat near-white (white letterboxing) are cut. Left on, they
// make the reader drop the price column and the total. Measured on a small copy, returned in the
// picture's own pixels.
function receiptRegion(picture, width, height) {
  const full = { x: 0, y: 0, w: width, h: height };
  const scale = Math.min(1, PROBE_SIDE / Math.max(width, height));
  const w = Math.max(1, Math.round(width * scale));
  const h = Math.max(1, Math.round(height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(picture, 0, 0, w, h);
  const grey = toGrey(ctx.getImageData(0, 0, w, h).data, w * h);
  // a run of pixels is border when it is dark, or light and flat (no print on it)
  const border = (values) => {
    let sum = 0;
    let squares = 0;
    for (const v of values) { sum += v; squares += v * v; }
    const mean = sum / values.length;
    return mean < DARK || (mean > LIGHT && Math.sqrt(Math.max(0, squares / values.length - mean * mean)) < FLAT);
  };
  const row = (y, x0, x1) => border(grey.subarray(y * w + x0, y * w + x1));
  const col = (x, y0, y1) => { const v = []; for (let y = y0; y < y1; y += 1) v.push(grey[y * w + x]); return border(v); };
  let top = 0;
  let bottom = h;
  while (top < bottom - 1 && row(top, 0, w)) top += 1;
  while (bottom > top + 1 && row(bottom - 1, 0, w)) bottom -= 1;
  let left = 0;
  let right = w;
  while (left < right - 1 && col(left, top, bottom)) left += 1;
  while (right > left + 1 && col(right - 1, top, bottom)) right -= 1;
  if (bottom - top < h * MIN_KEEP || right - left < w * MIN_KEEP) return full;
  if (top === 0 && left === 0 && bottom === h && right === w) return full;
  // one probe pixel of margin, so a cut never touches the paper
  const x = Math.max(0, Math.floor((left - 1) / scale));
  const y = Math.max(0, Math.floor((top - 1) / scale));
  return { x, y, w: Math.min(width, Math.ceil((right + 1) / scale)) - x, h: Math.min(height, Math.ceil((bottom + 1) / scale)) - y };
}

// A phone photo as the reader needs it: upright, the dark border cut, the receipt at a size it
// reads well, in grey. Two versions: `stretched` (the darkest 2% black and the lightest 2% white,
// for shadows and a dim room) and `plain` (grey only, for the second pass).
// Any failure: the original file for both, as before.
export async function prepareImages(file) {
  if (typeof document === "undefined" || !(file instanceof Blob)) return { stretched: file, plain: file };
  let picture = null;
  try {
    picture = await loadPicture(file);
    const width = picture.naturalWidth || picture.width;
    const height = picture.naturalHeight || picture.height;
    if (!width || !height) return { stretched: file, plain: file };
    const region = receiptRegion(picture, width, height);
    const scale = Math.min(MAX_UPSCALE, LONG_SIDE / Math.max(region.w, region.h));
    const w = Math.max(1, Math.round(region.w * scale));
    const h = Math.max(1, Math.round(region.h * scale));
    const canvas = (draw) => {
      const c = document.createElement("canvas");
      c.width = w;
      c.height = h;
      const ctx = c.getContext("2d", { willReadFrequently: true });
      const image = ctx.createImageData(w, h);
      draw(image.data);
      ctx.putImageData(image, 0, 0);
      return c;
    };
    const source = document.createElement("canvas");
    source.width = w;
    source.height = h;
    const sctx = source.getContext("2d", { willReadFrequently: true });
    sctx.imageSmoothingQuality = "high";
    sctx.drawImage(picture, region.x, region.y, region.w, region.h, 0, 0, w, h);
    const count = w * h;
    const grey = toGrey(sctx.getImageData(0, 0, w, h).data, count);
    const histogram = new Uint32Array(256);
    for (let i = 0; i < count; i += 1) histogram[grey[i]] += 1;
    let low = 0;
    let high = 255;
    for (let seen = 0; low < 255 && seen + histogram[low] <= count * 0.02; low += 1) seen += histogram[low];
    for (let seen = 0; high > 0 && seen + histogram[high] <= count * 0.02; high -= 1) seen += histogram[high];
    if (high - low < 16) { low = 0; high = 255; }
    const range = high - low;
    const paint = (px, value) => {
      for (let i = 0; i < count; i += 1) {
        const v = value(grey[i]);
        px[i * 4] = v;
        px[i * 4 + 1] = v;
        px[i * 4 + 2] = v;
        px[i * 4 + 3] = 255;
      }
    };
    return {
      stretched: canvas((px) => paint(px, (g) => ((g - low) * 255) / range)),
      plain: canvas((px) => paint(px, (g) => g)),
    };
  } catch (err) {
    return { stretched: file, plain: file };
  } finally {
    if (picture && typeof picture.close === "function") picture.close();
  }
}

// A sure total beats a best guess, which beats nothing.
function rank(result) {
  if (!result || !result.found) return 0;
  return result.guess ? 1 : 2;
}

const RIGHT_SHARE = 0.45; // the price column: the right 45% of the receipt
const DIGITS = "0123456789.,$-HK"; // what the price column pass may read
const BUDGET_MS = 10000; // no new pass starts after this long (about 10 s on an iPhone)

const isCanvas = (image) => typeof HTMLCanvasElement !== "undefined" && image instanceof HTMLCanvasElement;

// The right `share` of a picture, and where it starts (to put its words back in place).
function rightPart(image, share) {
  const dx = Math.round(image.width * (1 - share));
  const c = document.createElement("canvas");
  c.width = image.width - dx;
  c.height = image.height;
  c.getContext("2d").drawImage(image, dx, 0, c.width, c.height, 0, 0, c.width, c.height);
  return { canvas: c, dx };
}

// The picture turned by 90 or 270 degrees (a receipt photographed sideways).
function turn(image, degrees) {
  const c = document.createElement("canvas");
  c.width = image.height;
  c.height = image.width;
  const ctx = c.getContext("2d");
  ctx.translate(c.width / 2, c.height / 2);
  ctx.rotate((degrees * Math.PI) / 180);
  ctx.drawImage(image, -image.width / 2, -image.height / 2);
  return c;
}

// tesseract.js output as plain words and baselines (the shapes rows.js works on).
function wordsOf(data) {
  return (data.words || []).filter((w) => w.bbox).map((w) => ({ text: w.text, x0: w.bbox.x0, y0: w.bbox.y0, x1: w.bbox.x1, y1: w.bbox.y1 }));
}
function baselinesOf(data) {
  return (data.lines || []).map((l) => l.baseline).filter(Boolean);
}

// Read a receipt image and find its total. `parse(text)` asks the server (POST /api/receipt/parse)
// and returns its answer. Returns { text, result }: the text sent (shown as "What the reader saw"
// when nothing is found) and the server's answer. onProgress(percent, words) is called while it works.
// Pass 1 reads one column of lines (PSM 4) on the stretched picture. Only without a sure total, and
// while the time budget lasts, more passes run and their words are merged with the earlier ones,
// row by row (rows.js): the price column alone with a digits whitelist, the plain picture as one
// block (PSM 6, reads a big-print total), sparse text (PSM 11); then the picture turned 90 and 270
// degrees, read on its own. The best answer is kept; a sure total stops at once.
export async function readTotal(file, parse, onProgress) {
  onProgress(0, "Loading the offline reader");
  const images = await prepareImages(file);
  await loadScript();
  let words = "Reading the receipt";
  const worker = await window.Tesseract.createWorker(["eng", "chi_tra"], 1, {
    workerPath: new URL("worker.min.js", BASE).href,
    corePath: new URL("core", BASE).href,
    langPath: new URL("lang", BASE).href,
    workerBlobURL: false, // a same-origin worker file: the CSP allows no blob: scripts
    gzip: true,
    cacheMethod: "none",
    logger: (m) => {
      if (m.status === "recognizing text") onProgress(Math.round((m.progress || 0) * 100), words);
      else onProgress(0, "Loading the offline reader");
    },
  });
  const read = async (image, mode, extra = {}) => {
    await worker.setParameters({ tessedit_pageseg_mode: mode, preserve_interword_spaces: "1", tessedit_char_whitelist: "", ...extra });
    const { data } = await worker.recognize(image);
    return data;
  };
  const ask = async (raw) => {
    const text = trimText(raw || "");
    return { text, result: await parse(text) };
  };
  try {
    const started = Date.now();
    const first = await read(images.stretched, "4");
    let best = await ask(first.text);
    if (rank(best.result) === 2) return best;
    const slope = skewOf(baselinesOf(first));
    let seen = wordsOf(first);
    const canvas = isCanvas(images.stretched) && isCanvas(images.plain);
    const passes = [
      canvas && ["Reading the prices", async () => {
        const part = rightPart(images.plain, RIGHT_SHARE);
        return shiftWords(wordsOf(await read(part.canvas, "6", { tessedit_char_whitelist: DIGITS })), part.dx);
      }],
      ["Reading again", async () => wordsOf(await read(images.plain, "6"))],
      ["Reading scattered text", async () => wordsOf(await read(images.stretched, "11"))],
    ].filter(Boolean);
    for (const [label, run] of passes) {
      if (Date.now() - started > BUDGET_MS) return best;
      words = label;
      seen = mergeWords(seen, await run());
      const next = await ask(rebuildRows(seen, slope));
      if (rank(next.result) > rank(best.result)) best = next;
      if (rank(best.result) === 2) return best;
    }
    const sideways = canvas ? [() => turn(images.stretched, 90), () => turn(images.stretched, 270)] : [];
    for (const picture of sideways) {
      if (Date.now() - started > BUDGET_MS) return best;
      words = "Reading sideways";
      const next = await ask((await read(picture(), "4")).text);
      if (rank(next.result) > rank(best.result)) best = next;
      if (rank(best.result) === 2) return best;
    }
    return best;
  } finally {
    await worker.terminate();
  }
}

function bytes(text) {
  return new TextEncoder().encode(JSON.stringify({ text })).length;
}

// Fit the OCR text in one request: keep the first lines (merchant) and as many of the last
// lines (where the total is) as fit.
export function trimText(raw) {
  let lines = String(raw).split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  let text = lines.join("\n");
  while ((bytes(text) > MAX_BYTES || text.length > MAX_CHARS) && lines.length > 7) {
    lines = [...lines.slice(0, 6), ...lines.slice(7)];
    text = lines.join("\n");
  }
  while (bytes(text) > MAX_BYTES || text.length > MAX_CHARS) text = text.slice(0, -50);
  return text;
}
