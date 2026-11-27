// The guided tour and the auto-play demo: one story, step by step.
//
// The array between the two marker comments must stay plain JSON (double quotes, no
// trailing commas, no comments): backend/tests/test_frontend_files.py parses it.
//
// Fields:
//   id         unique name
//   title      bubble title
//   body       bubble text (guided)
//   autoBody   bubble text during auto-play, when the story differs (optional)
//   screen     the screen to show first: home | today | add | week | map | settings, or null
//              (home is the simulated home screen; on a real phone width it is skipped)
//   target     CSS selector the bubble points at, or null for a centred bubble
//   autoTarget the selector during auto-play, when it differs (optional)
//   dynamic    true when the target is drawn by JavaScript (not in index.html)
//   fallback   a selector from index.html, used when the target is missing
//   placement  auto | top | bottom | left | right | center
//   autoAction the scripted DEMO action run first during auto-play (tour.js ACTIONS), or null
//   autoOnly   true for steps that only make sense while the demo acts by itself
//
// Every number below is the DEMO sample week (Wed, HK$140 for today), checked in the code.
// The sample receipt (img/samples/receipt-1-noodle-bar.png) reads HK$50.60.

// STEPS-JSON-BEGIN
export const STEPS = [
  {
    "id": "welcome",
    "title": "Welcome to SSUST",
    "body": "A weekly budget for students, in a simulated phone. No bank connection, and no real money ever moves.",
    "screen": "today",
    "target": null,
    "dynamic": false,
    "fallback": null,
    "placement": "center",
    "autoAction": null,
    "autoOnly": false
  },
  {
    "id": "home",
    "title": "Widgets on the home screen",
    "body": "Widgets with what is left today, the 30 day status, your funds and quick add. Same numbers as the app.",
    "screen": "home",
    "target": "#home-widgets",
    "dynamic": false,
    "fallback": null,
    "placement": "bottom",
    "autoAction": null,
    "autoOnly": false
  },
  {
    "id": "left-today",
    "title": "Left to spend today",
    "body": "Food money left (Main meals plus Snacks) divided by the days left, today included. Here: HK$140 for today.",
    "screen": "today",
    "target": ".hero",
    "dynamic": true,
    "fallback": "#screen",
    "placement": "bottom",
    "autoAction": null,
    "autoOnly": false
  },
  {
    "id": "projection",
    "title": "The next 30 days",
    "body": "Your average spending over the next 30 days against your budget: Comfortable, On track or Spending too fast.",
    "screen": "today",
    "target": "#projection-card",
    "dynamic": true,
    "fallback": "#screen",
    "placement": "bottom",
    "autoAction": null,
    "autoOnly": false
  },
  {
    "id": "this-week",
    "title": "This week",
    "body": "This week only: at this pace, Snacks runs out around Saturday. Offline rules on this device.",
    "screen": "today",
    "target": ".ins-card",
    "dynamic": true,
    "fallback": "#screen",
    "placement": "top",
    "autoAction": null,
    "autoOnly": false
  },
  {
    "id": "tanks",
    "title": "Funds as tanks",
    "body": "Each fund as a tank, from your own entries, no bank. Fixed Bills never pays for others; Long-term Savings goes last.",
    "screen": "today",
    "target": "#funds-card .seg",
    "autoTarget": "#funds-card",
    "dynamic": true,
    "fallback": "#screen",
    "placement": "top",
    "autoAction": "showTanks",
    "autoOnly": false
  },
  {
    "id": "add-payment",
    "title": "Add a payment",
    "body": "Type the amount, use the slider or a quick amount, and pick a fund. One line shows what happens before you save.",
    "autoBody": "A HK$160 main meal is typed. Before saving, the line already says it is HK$20 more than what is left today.",
    "screen": "add",
    "target": "#amount",
    "autoTarget": "#preview",
    "dynamic": true,
    "fallback": "#screen",
    "placement": "bottom",
    "autoAction": "typeAmount",
    "autoOnly": false
  },
  {
    "id": "overspend",
    "title": "When a payment goes over",
    "body": "You choose where the extra comes from: Snacks, then flexible funds, and Long-term Savings only as a last resort.",
    "screen": "add",
    "target": "#save",
    "autoTarget": "#sheet .options",
    "dynamic": true,
    "fallback": "#screen",
    "placement": "top",
    "autoAction": "openCover",
    "autoOnly": false
  },
  {
    "id": "confirm",
    "title": "You choose, then confirm",
    "body": "Nothing is saved until Confirm. Here Experience pays the extra HK$20, so tomorrow stays HK$140.",
    "screen": null,
    "target": "#confirm-cover",
    "dynamic": true,
    "fallback": "#sheet",
    "placement": "top",
    "autoAction": "pickFlex",
    "autoOnly": true
  },
  {
    "id": "undo",
    "title": "Undo a payment",
    "body": "After a save, Undo puts every balance back exactly. Every payment of this week has an Undo button.",
    "autoBody": "Saved: Experience pays HK$20 into Main meals. Undo puts everything back exactly.",
    "screen": "today",
    "target": "[data-undo]",
    "autoTarget": "#funds-card",
    "dynamic": true,
    "fallback": "#screen",
    "placement": "top",
    "autoAction": "confirm",
    "autoOnly": false
  },
  {
    "id": "undone",
    "title": "Back to where it was",
    "body": "Undo, then Yes: the tanks fill back up and HK$140 is back for today.",
    "screen": null,
    "target": "#funds-card",
    "dynamic": true,
    "fallback": "#screen",
    "placement": "bottom",
    "autoAction": "undo",
    "autoOnly": true
  },
  {
    "id": "quick-add",
    "title": "Quick add from the widget",
    "body": "Type a payment in plain words on the home screen, like $50 KFC dinner. The widget picks the fund, says why, and checks for typos.",
    "autoBody": "$50 KFC dinner: KFC is a food chain, so Main meals. Saved through Add, with Undo: HK$90 left today.",
    "screen": "home",
    "target": "#home-quick",
    "dynamic": false,
    "fallback": null,
    "placement": "bottom",
    "autoAction": "quickAdd",
    "autoOnly": false
  },
  {
    "id": "scan",
    "title": "Scan a receipt",
    "body": "A photo or screenshot of a receipt is read on this device, offline. The total, the shop and a fund are filled in. It never saves by itself.",
    "autoBody": "A sample receipt is read offline: HK$50.60, the shop and Main meals are filled in. Not saved yet.",
    "screen": "add",
    "target": "#scan-btn",
    "autoTarget": "#scan-status",
    "dynamic": true,
    "fallback": "#sheet",
    "placement": "bottom",
    "autoAction": "scanSample",
    "autoOnly": false
  },
  {
    "id": "tap",
    "title": "Connected payments, simulated",
    "body": "Settings has Apple Wallet, Octopus and HSBC switches, all simulated in this demo. A tap adds a sample payment to review. Nothing here reads a bank. In the iPhone app, Apple Pay payments arrive through a Shortcuts automation.",
    "autoBody": "Apple Wallet is on and a simulated tap arrives. A sample: no card, no bank.",
    "screen": "settings",
    "target": "#connected-card",
    "autoTarget": "#notify",
    "dynamic": true,
    "fallback": "#screen",
    "placement": "bottom",
    "autoAction": "simulateTap",
    "autoOnly": false
  },
  {
    "id": "review",
    "title": "To review",
    "body": "The tap waits on Today with a fund picked from the shop name and a typo check. Confirm works like Add.",
    "screen": null,
    "target": "#review-card",
    "dynamic": true,
    "fallback": "#screen",
    "placement": "bottom",
    "autoAction": "openReview",
    "autoOnly": true
  },
  {
    "id": "widget",
    "title": "The widget follows",
    "body": "Confirmed: HK$18 to Main meals. The widget already shows HK$72 left today, like the app.",
    "screen": null,
    "target": "#home-widgets",
    "dynamic": false,
    "fallback": null,
    "placement": "bottom",
    "autoAction": "confirmReview",
    "autoOnly": true
  },
  {
    "id": "week",
    "title": "Where the money went",
    "body": "This week by fund, the biggest day, top notes and last week to compare. Your progress: the streak, stars for last week and badges.",
    "screen": "week",
    "target": ".ins-card",
    "dynamic": true,
    "fallback": "#screen",
    "placement": "bottom",
    "autoAction": null,
    "autoOnly": false
  },
  {
    "id": "map",
    "title": "Where can I eat with what is left?",
    "body": "Places near campus from OpenStreetMap. Menu ranges and chain prices show their source and date; the rest are estimates, not a real menu price.",
    "screen": "map",
    "target": "#osm-map",
    "dynamic": true,
    "fallback": "#screen",
    "placement": "bottom",
    "autoAction": null,
    "autoOnly": false
  },
  {
    "id": "done",
    "title": "That is SSUST",
    "body": "Know what you can spend today and where it buys a meal. Choose Live in Settings to start from HK$0.",
    "screen": "today",
    "target": null,
    "dynamic": false,
    "fallback": null,
    "placement": "center",
    "autoAction": null,
    "autoOnly": false
  }
];
// STEPS-JSON-END
