# Declutter audit

Goal: every screen answers one question in about 3 seconds. Same features, same rules, same
backend: only what is shown at first sight changed. Audited in DEMO in the phone frame.

Decisions: **keep**, **shorten**, **tap** (hidden behind a tap: a "Why?", "Numbers", "Source" or a
folded section), **remove**. Never removed: the Demo and Simulated markers, "Nothing is saved
until you confirm", Undo, and a way to reach every price source.

## Home screen (hero: what is left today)

| Element | Decision | Why |
| --- | --- | --- |
| Small widget: left today + status pill | keep | The hero of the home screen. |
| Small widget: "Updated 04:49" | remove | The status bar shows the time; the medium widget keeps it. |
| Medium widget: "Left today HK$140" + status pill | remove | Same number and pill as the small widget beside it. |
| Medium widget: six fund bars | keep, titled "Funds this week" | The only place on home that shows the funds. |
| Quick add header: "HK$140 left for food today" | shorten to "Quick add" | Third copy of the same number on one screen. |
| Quick add: "Try:" example chips | remove | The placeholder already shows "$50 KFC dinner". |
| Photo tab hint (two sentences) | shorten | "Read offline. You check it before it is saved." |

## Today (hero: Left to spend today + the Cooked meter)

| Element | Decision | Why |
| --- | --- | --- |
| Date, days left, HK$140, bar | keep | The answer to "what can I spend today". |
| "Spent on food today: HK$0 of HK$140" | shorten | "Spent HK$0 of HK$140", on one line with "Tomorrow HK$140". |
| "HK$700 food money left for 5 days" | remove | The funds card and the days left say it. |
| "Heads up: ..." notice | shorten | "HK$X of today's HK$Y used." |
| To review card | keep | Simulated tag, fund reason and Confirm stay. |
| Cooked gauge: "Chill · out of 100" | shorten to "out of 100" | The pill above already says Chill. |
| Cooked: the 3 factors | tap ("Why? 3 factors") | Already folded; label shortened. |
| Next 30 days: curve, legend, HK$0 day | keep | The one thing the card is for. |
| Next 30 days: totals and "Based on your last 3 days..." | tap ("Numbers") | Useful, not needed at first sight. |
| "This week" card: every warning in full | shorten | Headline + first warning; "See all n on Week". |
| Funds card: "44% of the week" under each fund | remove | Decorative; the amounts say it. |
| Funds card: flexible funds paragraph | tap ("What are flexible funds?") | A rule, not a number to read every day. |
| "Nothing logged today yet. Tap Add payment when you spend." | shorten | "Nothing yet today." |

## Add payment and the overspend sheet

| Element | Decision | Why |
| --- | --- | --- |
| Amount, slider, quick amounts, fund, note, Save | keep | The form. |
| Preview "... more than the HK$140 left today. Next, you choose where the extra comes from." | shorten | "HK$20 over today's HK$140. Next, you choose where it comes from." |
| Sheet intro "This HK$160 Main meals payment is HK$20 more than the HK$140 left for food today." | shorten | The title already says "the extra HK$20": "HK$160 Main meals payment, HK$140 left today." |
| Options with Tomorrow lines, Recommended, Last resort | keep | The choice itself. |
| "What changes" | keep (already folded) | |
| "Nothing is saved until you confirm. No real money moves: only your own budget shifts." | shorten | Keeps "Nothing is saved until you confirm." |

## Notifications

| Element | Decision | Why |
| --- | --- | --- |
| Payment notification body | shorten | "Tap to review. Simulated: no card, no bank." (Simulated tag kept.) |

## Camera

| Element | Decision | Why |
| --- | --- | --- |
| Viewfinder hint "Point at the total, or pick a photo or screenshot" | shorten | "Point at the total". |
| Viewfinder while reading | new: shows the image being read, progress on top | Nothing showed what was scanned. |
| Viewfinder with a result | compact, right above the result; shutter and samples hidden | Image and result readable together. |
| Sample thumbnails (44x58 crop of the top) | whole receipt, 80 px tall, name on 2 lines max | They looked like blank white boxes. |
| Gallery button (fake gradient) | last picked photo, else a photo icon | Shows what the button opens. |
| "Read from the receipt: ..." line, Why, fund chips | keep | Honest: you see what was read and why. |

## Map (hero: the list of places that fit)

| Element | Decision | Why |
| --- | --- | --- |
| Campus, distance, map, "Could fit today's HK$140" | keep | |
| Long honesty paragraph (menu ranges, chains, estimates) | shorten | "Menu and chain prices: tap Source. Other places: Estimated - not a real menu price." |
| "What the labels mean" | keep (already folded) | |
| "Tap one to see it on the map" | remove | Tapping a row is the obvious action. |
| Row: price in the grey line when the badge already shows it | remove | Same range twice on one row. |
| Row: menu/chain "why" line (repeats badge and source) | remove | Kept on estimate rows, where it says "not a real menu price". |
| Row: source link and date | tap ("Source") | The tag "menu" / "chain price" stays visible; the source is one tap away. |

## Week (hero: where the money went)

| Element | Decision | Why |
| --- | --- | --- |
| Week header, spent line, day rows | keep | |
| "This week: where the money went" | shorten | "Where the money went". |
| Breakdown bars | keep | The answer. |
| Notes (biggest day, top notes, flexible leftovers) | tap ("More notes") | Beyond the top items. |
| Big Next 30 days card | remove | Same curve as on Today. |

## Settings (hero: the weekly budget)

| Element | Decision | Why |
| --- | --- | --- |
| Weekly budget card | keep, first | |
| Two intro sentences | shorten | One line: "Saving starts a fresh demo week." |
| Mode | keep, second | Live or Demo must be obvious. |
| Connected payments | tap (folded card, "Simulated" tag on it) | Per-row "Simulated in this demo" replaced by one tag; "Nothing here reads your bank" kept. |
| Display (phone view) | tap (folded) | Rarely changed. |
| Demo & help | keep folded | |

## The demo video

The auto-play timeline still finds everything it needs, at the same step start times. Two
changes: the Map step now taps "Source" on the menu-range place (at 1:16.5) and on the chain
place (at 1:21.5) with real clicks, and the hook step points at the HK$140 amount
(`scrollTo` with `"aim": ".hero .big"`). The numbers are unchanged: HK$140, HK$90, HK$52,
HK$160 = HK$20 over, coffee -> Snacks, KFC -> Main meals.
