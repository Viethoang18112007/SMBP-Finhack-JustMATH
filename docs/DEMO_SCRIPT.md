# SSUST demo script

Generated from `frontend/js/demo-timeline.js` by `python tools/demo_script.py --write`: edit the
timeline, not this file. The auto-play (Settings > Demo & help > Play the demo, or "Show me around")
plays exactly this, in Demo mode, total 2:00. A small m:ss timer shows in a
corner while it plays (open the app with `?timer=0` to hide it). Pause, Back, Next, Skip and Restart
are on the caption; Back and Next jump to the exact start of a step.

Start it with `python run.py --demo` on a screen wider than 900 px (the phone frame).

## Record mode

For the screen recording, open `http://127.0.0.1:8765/?record=1` in a window wider than 1280 px.
The captions stay (title, text and progress bar, as subtitles), but the buttons, the step counter,
the timer, the demo controls beside the phone and the welcome tip are hidden. A pointer glides to
each control and shows the click before the real click happens. Press Space to start the demo and
Esc to stop it; when it ends, Space starts another take. Open `?cursor=1` for the pointer alone,
with the normal caption and controls.

| Time | Step | On screen | Say |
| --- | --- | --- | --- |
| 0:00 to 0:10 | A weekly budget for HK students | Five funds for the week. Today you can spend HK$140 on food, and the Cooked meter says: Chill. | Here's SSUST. The first thing I see: HK$140, what I can spend on food today. And the Cooked meter says: chill. |
| 0:10 to 0:22 | Quick add from the widget | "$50 KFC dinner": KFC is a food chain, so Main meals. Saved through the normal Add flow: HK$90 left today. | Logging takes three seconds. From the home-screen widget I type "fifty dollars, KFC dinner". Offline rules know KFC is a meal. Saved: HK$90 left. |
| 0:22 to 0:33 | A payment notification | An Apple Pay payment, HK$18 at 7-Eleven, arrives as a notification, then waits in the notification centre. Simulated here (no card, no bank); the iPhone app gets real ones through Shortcuts. | When I pay with my phone, the payment arrives by itself. Here it's simulated; in the iPhone app a Shortcuts automation sends the real one. |
| 0:33 to 0:43 | To review | HK$18 at 7-Eleven: no clear clue in the name, so Main meals (you can change it), and the typo check passed. Confirm uses the normal payment rules: HK$72 left today. | SSUST picks a fund from the shop name and says why; 7-Eleven gives no clear clue, so Main meals, and I can change it. One tap confirms. HK$72 left. |
| 0:43 to 0:57 | Scan a receipt | A real fusion receipt (card numbers covered) read offline: HK$15.10, the subtotal matched by the card line, Main meals. Add payment opens prefilled; you check it and Save: HK$56.90 left today. | Snap the receipt. This is a real fusion receipt, read offline. HK$15.10 and the fund are filled in, and I confirm before anything is saved. |
| 0:57 to 1:11 | When a payment goes over | HK$160 is HK$20 over today's HK$140. You choose: Snacks, then flexible funds, Long-term Savings last. Fixed Bills is never used. Undo puts it all back. | Now the moment that matters: a HK$160 meal, HK$20 over today. SSUST asks where it comes from: snacks first, then flexible funds, savings last. Bills are never touched, and undo puts it all back. |
| 1:11 to 1:25 | Where can I eat with what is left? | Near campus (HKUST in this demo): each place's own menu range or its chain's published price, with the source and the date. No verified dish price ships yet; the rest are estimates. | So where can I eat with what's left? The map shows places near campus that fit today's budget, with menu prices, their source and the date. |
| 1:25 to 1:41 | How cooked are you? | Three demo weeks: calm, tight, cooked. The score adds up three plain rules (pace, funds running out, savings used), not AI. The red dot: where you hit HK$0. | And the question every student asks: how cooked am I? Three plain rules: spending pace, funds running out, savings used. This week: cooked. The curve shows the day I'll hit zero, before it happens. |
| 1:41 to 1:52 | Set the week | Slide the weekly total, use the suggested split 40/5/15/10/10/20. A fund under its minimum gets a warning, never a block. | Setting up the week takes seconds: slide the total, take the suggested split. Go under a minimum and it warns you, never blocks. |
| 1:52 to 2:00 | Real and simulated | Real: the budget rules, offline OCR, cited price sources. Simulated: connected payments. The assistant is offline rules. No bank connection. | Real: the budget rules, offline receipts, cited prices. Simulated: connected payments. No bank login. That's SSUST. |

## What happens on screen

**0:00 A weekly budget for HK students**

- 0.0 s: show (screen=today)
- 0.3 s: scrollTo (selector=.hero, aim=.hero .big)
- 5.0 s: scrollTo (selector=#cooked-card)

**0:10 Quick add from the widget**

- 10.0 s: show (screen=home)
- 11.0 s: quickAdd

**0:22 A payment notification**

- 22.0 s: show (screen=home)
- 22.5 s: tap
- 27.0 s: openCenter
- 30.0 s: openPaymentNote

**0:33 To review**

- 33.0 s: scrollTo (selector=#review-card)
- 38.0 s: confirmReview

**0:43 Scan a receipt**

- 43.0 s: openCamera
- 45.0 s: scanInCamera (file=receipt-fusion.png)
- 51.5 s: checkInAdd
- 54.5 s: save

**0:57 When a payment goes over**

- 57.0 s: scenario (name=sample)
- 57.5 s: typeAmount
- 61.0 s: openCover
- 64.0 s: pickFlex
- 66.0 s: confirm
- 68.5 s: undo

**1:11 Where can I eat with what is left?**

- 71.0 s: show (screen=map)
- 74.5 s: scrollTo (selector=#screen .place.status-range_fits)
- 76.5 s: click (selector=#screen .place.status-range_fits + .place-src-box summary)
- 79.5 s: scrollTo (selector=#screen .place.status-chain_fits)
- 81.5 s: click (selector=#screen .place.status-chain_fits + .place-src-box summary)

**1:25 How cooked are you?**

- 85.0 s: show (screen=today)
- 85.5 s: scrollTo (selector=#cooked-card)
- 89.0 s: scenario (name=over)
- 89.3 s: scrollTo (selector=#cooked-card)
- 93.0 s: scenario (name=cooked)
- 93.3 s: scrollTo (selector=#cooked-card)
- 94.5 s: notify (kind=tooFast)
- 96.5 s: toggleFactors
- 99.0 s: scrollTo (selector=#projection-card)

**1:41 Set the week**

- 101.0 s: show (screen=settings)
- 101.6 s: scrollTo (selector=.stack-card)
- 102.8 s: slide (selector=#week-total-slider, to=2000, ms=2500)
- 106.0 s: click (selector=#use-suggested)
- 108.0 s: slide (selector=#main-slider, to=300, ms=2000)

**1:52 Real and simulated**

- 112.0 s: show (screen=home)

## Honest limits to keep in the narration

- Connected payments (Apple Pay, Octopus, HSBC) are simulated: sample payments, no card, no bank.
- In the iPhone app, bank cards in Apple Pay arrive by themselves through a Shortcuts automation.
  Octopus is not automatic: iOS gives no amount for an Octopus tap, so you type it in To review.
- The Assistant and the Cooked score are offline rules, not AI.
- The receipt is a real fusion receipt photo (card and reference numbers covered) read by offline OCR;
  OCR can misread, so you confirm before saving.
- Prices: each place's own menu range or a chain's published price, with source and date. No
  verified dish price ships yet. The rest are estimates.
- The Cooked step switches between three demo weeks (Sample week, Week already over, Cooked week).
