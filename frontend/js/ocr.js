// "Scan receipt": offline OCR in the browser with the vendored tesseract.js, loaded only when
// the button is used. The text read is sent to the server (POST /api/receipt/parse), which
// finds the total with tested rules. Nothing is saved here: the Add form is only pre-filled.

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

const LONG_SIDE = 2000; // pixels on the longer side: small receipt print stays readable, a phone stays fast
const MIN_LONG_SIDE = 1200;

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

// A phone photo as the reader needs it: upright, at a size it reads well, in grey with the
// contrast stretched (shadows and a dim room). Any failure: the original file, as before.
export async function prepareImage(file) {
  if (typeof document === "undefined" || !(file instanceof Blob)) return file;
  let picture = null;
  try {
    picture = await loadPicture(file);
    const width = picture.naturalWidth || picture.width;
    const height = picture.naturalHeight || picture.height;
    const long = Math.max(width, height);
    if (!long) return file;
    let scale = 1;
    if (long > LONG_SIDE) scale = LONG_SIDE / long;
    else if (long < MIN_LONG_SIDE) scale = Math.min(2, MIN_LONG_SIDE / long);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(picture, 0, 0, canvas.width, canvas.height);
    const image = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const px = image.data;
    const count = canvas.width * canvas.height;
    const grey = new Uint8ClampedArray(count);
    const histogram = new Uint32Array(256);
    for (let i = 0; i < count; i += 1) {
      const g = (px[i * 4] * 299 + px[i * 4 + 1] * 587 + px[i * 4 + 2] * 114) / 1000;
      grey[i] = g;
      histogram[grey[i]] += 1;
    }
    // The darkest 2% become black and the lightest 2% white.
    let low = 0;
    let high = 255;
    for (let seen = 0; low < 255 && seen + histogram[low] <= count * 0.02; low += 1) seen += histogram[low];
    for (let seen = 0; high > 0 && seen + histogram[high] <= count * 0.02; high -= 1) seen += histogram[high];
    if (high - low < 16) { low = 0; high = 255; }
    const range = high - low;
    for (let i = 0; i < count; i += 1) {
      const v = ((grey[i] - low) * 255) / range;
      px[i * 4] = v;
      px[i * 4 + 1] = v;
      px[i * 4 + 2] = v;
      px[i * 4 + 3] = 255;
    }
    ctx.putImageData(image, 0, 0);
    return canvas;
  } catch (err) {
    return file;
  } finally {
    if (picture && typeof picture.close === "function") picture.close();
  }
}

// Read the text on a receipt image. onProgress(percent, words) is called while it works.
export async function readReceipt(file, onProgress) {
  onProgress(0, "Loading the offline reader");
  const image = await prepareImage(file);
  await loadScript();
  const worker = await window.Tesseract.createWorker(["eng", "chi_tra"], 1, {
    workerPath: new URL("worker.min.js", BASE).href,
    corePath: new URL("core", BASE).href,
    langPath: new URL("lang", BASE).href,
    workerBlobURL: false, // a same-origin worker file: the CSP allows no blob: scripts
    gzip: true,
    cacheMethod: "none",
    logger: (m) => {
      if (m.status === "recognizing text") onProgress(Math.round((m.progress || 0) * 100), "Reading the receipt");
      else onProgress(0, "Loading the offline reader");
    },
  });
  try {
    // One column of lines (PSM 4) keeps "TOTAL ...... 48.00" on one line; automatic layout
    // splits the two columns into separate blocks.
    await worker.setParameters({ tessedit_pageseg_mode: "4", preserve_interword_spaces: "1" });
    const { data } = await worker.recognize(image);
    return data.text || "";
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
