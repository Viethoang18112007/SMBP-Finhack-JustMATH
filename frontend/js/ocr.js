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

// Read the text on a receipt image. onProgress(percent, words) is called while it works.
export async function readReceipt(file, onProgress) {
  onProgress(0, "Loading the offline reader");
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
    const { data } = await worker.recognize(file);
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
