"""Check the auto-play timeline and write docs/DEMO_SCRIPT.md from it.

    python tools/demo_script.py           # prints every step and the total; exit 1 if over 2:00
    python tools/demo_script.py --write   # also rewrites docs/DEMO_SCRIPT.md

The timeline is the JSON array in frontend/js/demo-timeline.js (between the TIMELINE-JSON markers).
Standard library only.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMELINE_FILE = ROOT / "frontend" / "js" / "demo-timeline.js"
SCRIPT_FILE = ROOT / "docs" / "DEMO_SCRIPT.md"
MAX_SECONDS = 120  # 2:00, the length of the video


def load_timeline(path=TIMELINE_FILE):
    text = Path(path).read_text(encoding="utf-8")
    found = re.search(r"// TIMELINE-JSON-BEGIN\s*export const TIMELINE = (\[.*\]);\s*// TIMELINE-JSON-END", text, re.DOTALL)
    if not found:
        raise ValueError("TIMELINE must sit between the TIMELINE-JSON markers")
    return json.loads(found.group(1))


def clock(seconds):
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def problems(timeline):
    """Every way the timeline is broken, as text (empty when it is fine)."""
    out = []
    if not timeline:
        return ["the timeline is empty"]
    if timeline[0]["start"] != 0:
        out.append("the first step must start at 0")
    for before, after in zip(timeline, timeline[1:]):
        if after["start"] != before["end"]:
            out.append(f"{after['id']} starts at {after['start']}, not at the end of {before['id']} ({before['end']})")
    for step in timeline:
        length = step["end"] - step["start"]
        if length <= 0:
            out.append(f"{step['id']} has no length")
        for action in step["actions"]:
            if not 0 <= action["at"] < length:
                out.append(f"{step['id']}: action {action['do']} at {action['at']} s is outside the step")
    total = timeline[-1]["end"]
    if total > MAX_SECONDS:
        out.append(f"total {clock(total)} is over {clock(MAX_SECONDS)}")
    return out


def markdown(timeline):
    lines = [
        "# SSUST demo script",
        "",
        "Generated from `frontend/js/demo-timeline.js` by `python tools/demo_script.py --write`: edit the",
        "timeline, not this file. The auto-play (Settings > Demo & help > Play the demo, or \"Show me around\")",
        f"plays exactly this, in Demo mode, total {clock(timeline[-1]['end'])}. A small m:ss timer shows in a",
        "corner while it plays (open the app with `?timer=0` to hide it). Pause, Back, Next, Skip and Restart",
        "are on the caption; Back and Next jump to the exact start of a step.",
        "",
        "Start it with `python run.py --demo` on a screen wider than 900 px (the phone frame).",
        "",
        "## Record mode",
        "",
        "For the screen recording, open `http://127.0.0.1:8765/?record=1` in a window wider than 1280 px.",
        "The captions stay (title, text and progress bar, as subtitles), but the buttons, the step counter,",
        "the timer, the demo controls beside the phone and the welcome tip are hidden. A pointer glides to",
        "each control and shows the click before the real click happens. Press Space to start the demo and",
        "Esc to stop it; when it ends, Space starts another take. Open `?cursor=1` for the pointer alone,",
        "with the normal caption and controls.",
        "",
        "| Time | Step | On screen | Say |",
        "| --- | --- | --- | --- |",
    ]
    for step in timeline:
        cell = lambda text: text.replace("|", "\\|")  # noqa: E731
        lines.append(f"| {clock(step['start'])} to {clock(step['end'])} | {cell(step['title'])} | "
                     f"{cell(step['caption'])} | {cell(step['narration'])} |")
    lines += [
        "",
        "## What happens on screen",
        "",
    ]
    for step in timeline:
        lines.append(f"**{clock(step['start'])} {step['title']}**")
        lines.append("")
        for action in step["actions"]:
            args = ", ".join(f"{k}={v}" for k, v in action.items() if k not in ("at", "do"))
            at = step["start"] + action["at"]
            lines.append(f"- {at:.1f} s: {action['do']}{f' ({args})' if args else ''}")
        lines.append("")
    lines += [
        "## Honest limits to keep in the narration",
        "",
        "- Connected payments (Apple Pay, Octopus, HSBC) are simulated: sample payments, no card, no bank.",
        "- In the iPhone app, bank cards in Apple Pay arrive by themselves through a Shortcuts automation.",
        "  Octopus is not automatic: iOS gives no amount for an Octopus tap, so you type it in To review.",
        "- The Assistant and the Cooked score are offline rules, not AI.",
        "- The receipt is a sample image read by offline OCR; OCR can misread, so you confirm before saving.",
        "- Prices: each place's own menu range or a chain's published price, with source and date. No",
        "  verified dish price ships yet. The rest are estimates.",
        "- The Cooked step switches between three demo weeks (Sample week, Week already over, Cooked week).",
        "",
    ]
    return "\n".join(lines)


def main(argv):
    timeline = load_timeline()
    for step in timeline:
        print(f"{clock(step['start'])}-{clock(step['end'])}  {step['id']}: {len(step['actions'])} action(s)")
    total = timeline[-1]["end"]
    print(f"Total: {clock(total)} ({total} s), limit {clock(MAX_SECONDS)}")
    found = problems(timeline)
    for problem in found:
        print(f"  problem: {problem}")
    if "--write" in argv and not found:
        SCRIPT_FILE.write_text(markdown(timeline), encoding="utf-8")
        print(f"Wrote {SCRIPT_FILE}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
