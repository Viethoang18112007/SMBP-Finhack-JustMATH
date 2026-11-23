# SSUST UX audit

Screens captured with a headless browser at 390x844 (mobile) and 1366x900 (desktop).
Before: `docs/ux-before/`. Reference app: `docs/ux-reference/`. After: `docs/ux-after/`.

## What makes the reference easy to use

The reference is a small money transfer prototype (balance card, one send form, review, success).
We take its patterns only, not its look, brand or features.

- **One number on top.** The balance is the only big number (`mobile-02-dashboard-send.png`).
- **One primary action per step.** Send form: Continue. Review: Confirm (Back is outlined). Success: Done.
- **Three steps, each one small.** Amount, then review, then a success card (`mobile-04`, `05`, `07`).
- **The primary button can't fail.** Continue stays disabled while the amount is empty or above the balance (`mobile-03-empty-disabled.png`).
- **The big field is the form.** A large amount field with a currency prefix, `inputmode="decimal"`.
- **Review shows only what changes.** To, amount, fee, total. No rules text.
- **Clear success state.** A check, the amount, one Done button, and the balance on top already updated.
- **Calm spacing.** One card style, one radius, generous padding, one accent colour.
- **Desktop is the same column, centred** (`desktop-02-dashboard-send.png`), no side panel.

## Problems found in SSUST, and the fix

Screens refer to `docs/ux-before/`.

### Global shell
- Walkthrough panel (`#notes`) is a wall of text under the app on every mobile screen and beside it on desktop (`mobile-14-map.png`, `desktop-02-today.png`).
  **Fix:** remove it from the UI; move the script to `docs/DEMO_SCRIPT.md`. Demo and tour stay in the welcome card, the header help button and Settings.
- Header has brand, subtitle, Tour pill, LIVE/DEMO switch and a full-width badge (`mobile-02-today.png`).
  **Fix:** one slim bar: brand, a small mode chip (DEMO is amber and obvious, LIVE is quiet), a "?" help button. The switch moves to Settings.
- "New here?" card has 4 buttons and covers the funds list (`mobile-01-today-offer.png`).
  **Fix:** one welcome card in the page flow (never overlapping): "Show me around" and "Skip".
- The nav is text only and the Add button scrolls away.
  **Fix:** nav with icons and labels; a sticky "Add payment" button above the nav on Today, Week and Day.
- Desktop shows a phone mock-up beside a text column.
  **Fix:** one centred app column, no side panel.

### Today
- "Today's line HK$140 = food left HK$700 ÷ 5 days" is jargon (`mobile-02-today.png`).
  **Fix:** "HK$700 food money left for 5 days" and "Tomorrow: HK$140".
- "0 payments today" repeats "Spent on food today: HK$0".
  **Fix:** remove the count; the bar caption says "HK$48 spent of HK$140".
- The bar has no label or meaning.
  **Fix:** it is "spent vs today's budget", green, then amber near the limit, red when over.
- Funds show only what is left.
  **Fix:** "left / weekly" with a thin bar per fund, coloured by health. Tanks stays as a quiet second view.
- Undo is clipped under the amount in "Today's payments" (`mobile-08-saved.png`).
  **Fix:** one row: name and note, amount, Undo. The confirm step opens under the row.

### Add payment
- Full screen with a 6-line rules paragraph (`mobile-04-add-empty.png`).
  **Fix:** a bottom sheet over Today: big amount field, fund chips, optional note, live preview, Save and a quiet Cancel.
- Doubled focus outline on the amount field.
  **Fix:** one focus style (underline colour + the shared focus ring only for keyboard focus).
- Fund names differ: "Main meal" / "Main meals", "Fixed bill" / "Fixed Bills" / "Fixed bills (HK$)".
  **Fix:** one set everywhere: Main meals, Snacks, Fixed Bills, Experience, Development, Long-term Savings (the server's names).
- Overspend modal: long text and a before/after table per option (`mobile-07-overspend.png`).
  **Fix:** two option cards, "Take HK$8 from Snacks" with "Tomorrow: HK$140 → HK$138", recommended one marked and preselected, fund changes folded in "Details", one Confirm.
- No clear success state; the page just jumps.
  **Fix:** a toast "Saved HK$48 · Main meals" with Undo (still a two-step undo), Today updates with a count-up.
- Raw server messages could reach the user.
  **Fix:** errors are mapped to plain words and shown under the field.

### Week
- Rows repeat the weekday ("Mon 9 Nov" / "Mon") (`mobile-11-week.png`).
  **Fix:** the sublabel only says Today, Ahead, Near limit or Over.
- Two big disabled "Previous week / Next week" buttons.
  **Fix:** compact arrow buttons beside the date range.
- Colour legend sentence.
  **Fix:** the colour and its label are on the row.

### Map
- Five campus chips, radius select, More layers, fit toggle, a yellow warning and a legend sit above the map (`mobile-14-map.png`).
  **Fix:** campus and distance as two compact selects in one row, then the map. Under it: one short estimate line, the fit toggle and the list. The legend is a "?" disclosure.
- The list rows mix name, status, type and a long reason.
  **Fix:** name, type, distance, price range, one status chip. The reason shows on the selected place.

### Settings
- Six inputs under "FIVE FUNDS", a vague "Use these numbers" button, footnotes (`mobile-15b-settings-full.png`).
  **Fix:** "Weekly budget" with HK$ inputs, a running total, "Save weekly budget". Mode switch in its own card. Demo weeks, tour, play demo and "show tips again" folded in "Demo & help".

### First launch (LIVE, empty data)
- A card says "Type the five ZUNO funds", then sends you to Settings (`mobile-20-live-first-launch.png`).
  **Fix:** Today itself is the setup: "Set your weekly budget", prefilled amounts, total, one button, then Today.

## Before / after

Same scenario, same numbers. Pairs: `docs/ux-before/<size>-NN-*.png` and `docs/ux-after/<size>-NN-*.png`.

| Screen | Before | After | Why |
| --- | --- | --- | --- |
| Shell | Walkthrough text under/beside the app, 5-part header, 4-button card over the funds (`01-today-offer`) | Slim header (brand, Demo/Live chip, "?"), welcome card in the flow with one action and Skip (`01-today-welcome`) | The first screen says one thing: what you can spend today |
| Today | "Today's line = food left ÷ days", payment count, balances only (`02-today`) | "HK$700 food money left for 5 days", "Tomorrow: HK$140", spent bar "of HK$140", left / weekly with a bar per fund (`02-today`) | Plain words; health of each fund at a glance |
| Add payment | Full screen with a rules paragraph (`04-add-empty`) | Bottom sheet: big HK$ field, chips, note, live result line, Save / Cancel (`04-add-empty`, `05-add-filled`) | Open, amount, fund, Save: 3 taps and typing |
| Errors | Message far from the field | Plain words under the field, red underline (`06-add-error`) | You see what to fix where you fix it |
| Overspend | Paragraph + before/after table per option (`07-overspend`) | Two cards "Take HK$8 from Snacks · Tomorrow HK$140 → HK$138", Recommended preselected, details folded, one Confirm, Back (`07-overspend`, `07b-overspend-details`) | The choice reads as a consequence, not a rule |
| After save | Screen jumps, Undo clipped under the amount (`08-saved`) | Toast "Saved HK$48 · Main meals · HK$92 left today" with Undo; row shows name, amount, Undo on one line (`08-saved-toast`, `09-undo-confirm`) | Clear success and a safe way back |
| Week | Weekday twice, big disabled buttons, colour legend sentence (`11-week`) | Arrows beside the range, "Today · on track" on the row, one summary line (`11-week`, `12-day`) | Less to read, state on the row |
| Map | 5 chips, select, layers, toggle, warning and legend above the map (`14-map`) | Two selects, then the map; one estimate line, toggle, list with type · distance · range and one chip (`14-map`, `14c-map-selected`) | The map is the answer; honesty stays one line away |
| Settings | "FIVE FUNDS", "Use these numbers", footnotes (`15-settings`) | "Weekly budget" with HK$ fields, running total, "Save weekly budget"; Mode card; Demo & help folded (`15-settings`, `15b-settings-help`) | One primary action; demo tools out of the way |
| First LIVE launch | Card pointing to Settings (`20-live-first-launch`) | Today is the setup: suggested amounts, total, "Start my week" (`20-live-first-launch`, `21-live-today`) | One screen from empty to a working day |
| Tour | 10 / 12 steps on the old screens | Same steps and timing on the new screens (`16-tour-1`, `17-tour-2`, `17b-tour-5`) | Copy matches what is on screen |

Checked by clicking, at 360, 390, 768 and 1366 px: no horizontal scroll and no element outside the app.
Demo numbers unchanged: HK$140 today; HK$48 meal gives HK$92; HK$100 meal offers Snacks (tomorrow HK$138)
or Experience (tomorrow HK$140); Experience HK$150 takes HK$30 from Development (HK$80 → HK$50);
"Week already over" HK$30 comes from Long-term Savings (HK$500 → HK$470).

Tests changed (same intent, new markup): the header test now checks the mode chip in the header and the
switch in Settings; the walkthrough test checks the panel left the UI and the script exists in docs; the
preview test checks the new plain wording ("Today left:", "you choose where the extra comes from").
