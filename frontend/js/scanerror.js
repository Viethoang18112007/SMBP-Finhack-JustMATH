// What Add payment says when a receipt scan fails, by the stage that failed, so a failed scan is
// never silent and the student (and whoever checks the report) knows where it stopped. Pure: no DOM,
// no globals, no imports.

export const SCAN_FAILED = "Could not read this image. Type the amount in.";
const REASON_MAX = 120;

// stage: "plugin" (the phone's scanner gave an error, err.code), "no_pages" (it returned no page),
// "no_text" (pages but no text), "server" (the text went to the server: err.fromServer when it refused).
export function scanFailure(stage, err) {
  const code = err && typeof err.code === "string" && /^[a-z_]{1,30}$/.test(err.code) ? err.code : "";
  if (stage === "plugin") return `The phone's scanner failed${code ? ` (${code})` : ""}. Scan again, or type the amount in.`;
  if (stage === "no_pages") return "The scanner returned no pages. Scan again, or type the amount in.";
  if (stage === "no_text") return "No text was read on the receipt. Scan it again flat, in good light, or type the amount in.";
  if (stage === "server") {
    if (!err || !err.fromServer) {
      return "The server did not answer, so the total could not be found. Check the connection and scan again, or type the amount in.";
    }
    const reason = String(err.message || "").trim().replace(/\.$/, "").slice(0, REASON_MAX) || "no reason given";
    return `The server refused: ${reason}. Type the amount in.`;
  }
  return SCAN_FAILED;
}
