// Receipts in the iPhone app: read on the phone with Apple's on-device text recognition, through the
// app's own ReceiptScanner plugin (ios/App/App/ReceiptScanner.swift). No photo leaves the phone: the
// caller sends only the text to the server (POST /api/receipt/parse) to find the total.
// On the web, or in an app build without the plugin, nativeScanner() is null and the callers use the
// offline tesseract.js reader (ocr.js) as before.

import { NATIVE } from "./config.js";
import { trimText } from "./ocr.js";
import { textOfPages } from "./rows.js";

// The plugin, or null. Never throws.
export function nativeScanner() {
  if (!NATIVE) return null;
  try {
    const cap = window.Capacitor;
    if (typeof cap.isPluginAvailable === "function" && !cap.isPluginAvailable("ReceiptScanner")) return null;
    const plugin = cap.Plugins && cap.Plugins.ReceiptScanner;
    return plugin && typeof plugin.scan === "function" && typeof plugin.recognize === "function" ? plugin : null;
  } catch (err) {
    return null;
  }
}

// A picked photo as base64, without the "data:...;base64," head.
function base64Of(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).replace(/^data:[^,]*,/, ""));
    reader.onerror = () => reject(new Error("no image"));
    reader.readAsDataURL(file);
  });
}

// The receipt's text: from the document camera when there is no file, else from the picked photo.
// Rejects with the plugin's error (err.code: cancelled, camera_denied, unavailable, busy, failed, bad_image).
export async function readNative(scanner, file) {
  const answer = file ? await scanner.recognize({ image: await base64Of(file) }) : await scanner.scan({});
  return trimText(textOfPages(answer && answer.pages));
}
