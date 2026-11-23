// The auto-play demo as one timeline, for a 2-minute video (total 2:00).
//
// The array between the two marker comments must stay plain JSON: backend/tests/test_frontend_files.py
// checks it and tools/demo_script.py writes docs/DEMO_SCRIPT.md from it.
//
// Fields:
//   id, title    step name and the caption title
//   start, end   absolute times in seconds from the start of the video
//   caption      the short text shown on screen
//   narration    what to say over it (spoken English, one or two short sentences)
//   setup        actions that rebuild the state this step starts from, after a demo reset
//                (Next / Back / Restart jump here)
//   actions      { "at": seconds after the step start, "do": action name in tour.js TIMELINE_ACTIONS, ...args }
//                (scrollTo takes "aim": a selector the record-mode pointer points at, like the amount)
//
// Every number in a caption is the DEMO data at that moment, checked in the app.

// TIMELINE-JSON-BEGIN
export const TIMELINE = [
  {
    "id": "hook",
    "title": "A weekly budget for HK students",
    "start": 0,
    "end": 10,
    "caption": "Five funds for the week. Today you can spend HK$140 on food, and the Cooked meter says: Chill.",
    "narration": "Here's SSUST. The first thing I see: HK$140, what I can spend on food today. And the Cooked meter says: chill.",
    "setup": [],
    "actions": [
      {"at": 0, "do": "show", "screen": "today"},
      {"at": 0.3, "do": "scrollTo", "selector": ".hero", "aim": ".hero .big"},
      {"at": 5, "do": "scrollTo", "selector": "#cooked-card"}
    ]
  },
  {
    "id": "quick-add",
    "title": "Quick add from the widget",
    "start": 10,
    "end": 22,
    "caption": "\"$50 KFC dinner\": KFC is a food chain, so Main meals. Saved through the normal Add flow: HK$90 left today.",
    "narration": "Logging takes three seconds. From the home-screen widget I type \"fifty dollars, KFC dinner\". Offline rules know KFC is a meal. Saved: HK$90 left.",
    "setup": [],
    "actions": [
      {"at": 0, "do": "show", "screen": "home"},
      {"at": 1, "do": "quickAdd"}
    ]
  },
  {
    "id": "notification",
    "title": "A payment notification",
    "start": 22,
    "end": 33,
    "caption": "A simulated Apple Pay tap arrives as a notification, then waits in the notification centre. Connected payments are simulated: no card, no bank.",
    "narration": "When I pay with my phone, the payment arrives as a notification. In this prototype it's simulated: no real card, no bank.",
    "setup": [{"do": "addPayment", "amount": "50", "category": "main", "note": "KFC dinner"}],
    "actions": [
      {"at": 0, "do": "show", "screen": "home"},
      {"at": 0.5, "do": "tap"},
      {"at": 5, "do": "openCenter"},
      {"at": 8, "do": "openPaymentNote"}
    ]
  },
  {
    "id": "review",
    "title": "To review",
    "start": 33,
    "end": 43,
    "caption": "HK$38 at a sample coffee kiosk: Snacks, picked from \"coffee\", and the typo check passed. Confirm uses the normal payment rules: HK$52 left today.",
    "narration": "SSUST guesses the fund from the shop name, coffee means Snacks, and checks the amount for typos. One tap confirms. HK$52 left.",
    "setup": [{"do": "addPayment", "amount": "50", "category": "main", "note": "KFC dinner"}, {"do": "tap"}, {"do": "show", "screen": "today"}],
    "actions": [
      {"at": 0, "do": "scrollTo", "selector": "#review-card"},
      {"at": 5, "do": "confirmReview"}
    ]
  },
  {
    "id": "receipt",
    "title": "Scan a receipt",
    "start": 43,
    "end": 57,
    "caption": "Camera screen, a sample receipt read offline on the phone: HK$50.60, the shop, Main meals. Add payment opens prefilled; you check it and Save.",
    "narration": "Paid cash? Snap the receipt. It's read offline, on the phone. The total and the fund are filled in, and I confirm before anything is saved.",
    "setup": [{"do": "addPayment", "amount": "50", "category": "main", "note": "KFC dinner"}, {"do": "tap"}, {"do": "show", "screen": "today"}, {"do": "confirmReview"}],
    "actions": [
      {"at": 0, "do": "openCamera"},
      {"at": 2, "do": "scanInCamera", "file": "receipt-1-noodle-bar.png"},
      {"at": 8.5, "do": "checkInAdd"},
      {"at": 11.5, "do": "save"}
    ]
  },
  {
    "id": "overspend",
    "title": "When a payment goes over",
    "start": 57,
    "end": 71,
    "caption": "HK$160 is HK$20 over today's HK$140. You choose: Snacks, then flexible funds, Long-term Savings last. Fixed Bills is never used. Undo puts it all back.",
    "narration": "Now the moment that matters: a HK$160 meal, HK$20 over today. SSUST asks where it comes from: snacks first, then flexible funds, savings last. Bills are never touched, and undo puts it all back.",
    "setup": [],
    "actions": [
      {"at": 0, "do": "scenario", "name": "sample"},
      {"at": 0.5, "do": "typeAmount"},
      {"at": 4, "do": "openCover"},
      {"at": 7, "do": "pickFlex"},
      {"at": 9, "do": "confirm"},
      {"at": 11.5, "do": "undo"}
    ]
  },
  {
    "id": "map",
    "title": "Where can I eat with what is left?",
    "start": 71,
    "end": 85,
    "caption": "Near campus (HKUST in this demo): each place's own menu range or its chain's published price, with the source and the date. No verified dish price ships yet; the rest are estimates.",
    "narration": "So where can I eat with what's left? The map shows places near campus that fit today's budget, with menu prices, their source and the date.",
    "setup": [],
    "actions": [
      {"at": 0, "do": "show", "screen": "map"},
      {"at": 3.5, "do": "scrollTo", "selector": "#screen .place.status-range_fits"},
      {"at": 5.5, "do": "click", "selector": "#screen .place.status-range_fits + .place-src-box summary"},
      {"at": 8.5, "do": "scrollTo", "selector": "#screen .place.status-chain_fits"},
      {"at": 10.5, "do": "click", "selector": "#screen .place.status-chain_fits + .place-src-box summary"}
    ]
  },
  {
    "id": "cooked",
    "title": "How cooked are you?",
    "start": 85,
    "end": 101,
    "caption": "Three demo weeks: calm, tight, cooked. The score adds up three plain rules (pace, funds running out, savings used), not AI. The red dot: where you hit HK$0.",
    "narration": "And the question every student asks: how cooked am I? Three plain rules: spending pace, funds running out, savings used. This week: cooked. The curve shows the day I'll hit zero, before it happens.",
    "setup": [],
    "actions": [
      {"at": 0, "do": "show", "screen": "today"},
      {"at": 0.5, "do": "scrollTo", "selector": "#cooked-card"},
      {"at": 4, "do": "scenario", "name": "over"},
      {"at": 4.3, "do": "scrollTo", "selector": "#cooked-card"},
      {"at": 8, "do": "scenario", "name": "cooked"},
      {"at": 8.3, "do": "scrollTo", "selector": "#cooked-card"},
      {"at": 9.5, "do": "notify", "kind": "tooFast"},
      {"at": 11.5, "do": "toggleFactors"},
      {"at": 14, "do": "scrollTo", "selector": "#projection-card"}
    ]
  },
  {
    "id": "budget",
    "title": "Set the week",
    "start": 101,
    "end": 112,
    "caption": "Slide the weekly total, use the suggested split 40/5/15/10/10/20. A fund under its minimum gets a warning, never a block.",
    "narration": "Setting up the week takes seconds: slide the total, take the suggested split. Go under a minimum and it warns you, never blocks.",
    "setup": [{"do": "scenario", "name": "cooked"}],
    "actions": [
      {"at": 0, "do": "show", "screen": "settings"},
      {"at": 0.6, "do": "scrollTo", "selector": ".stack-card"},
      {"at": 1.8, "do": "slide", "selector": "#week-total-slider", "to": 2000, "ms": 2500},
      {"at": 5, "do": "click", "selector": "#use-suggested"},
      {"at": 7, "do": "slide", "selector": "#main-slider", "to": 300, "ms": 2000}
    ]
  },
  {
    "id": "outro",
    "title": "Real and simulated",
    "start": 112,
    "end": 120,
    "caption": "Real: the budget rules, offline OCR, cited price sources. Simulated: connected payments. The assistant is offline rules. No bank connection.",
    "narration": "Real: the budget rules, offline receipts, cited prices. Simulated: connected payments. No bank, no cloud. That's SSUST.",
    "setup": [],
    "actions": [
      {"at": 0, "do": "show", "screen": "home"}
    ]
  }
];
// TIMELINE-JSON-END

export const TOTAL_SECONDS = TIMELINE[TIMELINE.length - 1].end;
