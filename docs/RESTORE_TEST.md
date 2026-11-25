# Restore after a server wipe on a real iPhone: manual checklist

The hosted server (Render free plan, service `ssust-api`) loses its disk whenever it restarts or sleeps. The iPhone app keeps its own copy of this phone's data (Capacitor Preferences, refreshed from `GET /api/backup` after each change and at each app open) and sends it back with `POST /api/restore` when the server says it has nothing for this phone. This cannot be tested on Windows or in CI, so run this list on a real iPhone after a TestFlight build that changes it.

## Before you start

- Push the branch, then Render > `ssust-api` > **Manual Deploy** > Deploy latest commit. Wait until the deploy is live.
- Install the latest build from TestFlight. Open SSUST once and wait for Today to load.
- The Apple Pay automation from Settings > **Apple Pay and widget** is set up (needed for step 4).
- Have a second device or a computer to restart the Render service.

## 1. Use the app

1. Settings: set a weekly budget (for example HK$1,000 split with **Use suggested split**).
2. Add three payments: one in Main meals, one in Snacks, one with **Log a meal here** on the map.
3. Undo one of them from the toast or the payment row.
4. Send feedback (Feedback tab, 4 stars, a short line).
5. Close SSUST (swipe it away), open it again, wait 5 seconds, then close it again. This makes sure the copy on the phone is fresh.
- [ ] Write down: what is left today, each fund's amount, the payments listed, the streak.

## 2. Wipe the server

1. Render > `ssust-api` > **Manual Deploy** > Deploy latest commit (or **Restart service**). Wait until it is live again.
2. Optional check from a computer: `curl -H "X-SSUST-Device: <this phone's id>" https://ssust-api.onrender.com/api/state` shows `"fresh": true`. (The id is in Settings > Apple Pay and widget.)

## 3. Reopen the app: the data comes back

1. Open SSUST.
- [ ] A short banner says **Your data was restored from this phone.**
- [ ] Today shows the same numbers as in step 1: left today, every fund, the payments, the undone payment still undone.
- [ ] Week shows the same payments; the streak and stars are the same; Feedback still lists the feedback.
- [ ] Close and reopen SSUST: no banner this time (nothing to restore), same numbers.

## 4. An Apple Pay payment made while the server was empty

1. Wipe the server again (step 2). Do NOT open SSUST.
2. Pay a small amount with Apple Pay so the Shortcuts automation runs.
3. Open SSUST.
- [ ] **Your data was restored from this phone.** shows, and every number from step 1 is back.
- [ ] The Apple Pay payment from this step waits in Today under **To review**, with the right amount and shop.
- [ ] Confirm it into a fund: the fund goes down by that amount, nothing else changes.
- [ ] Settings > Apple Pay and widget shows this payment as the last message.

## 5. Server asleep or out of reach

1. Turn on Airplane mode, then open SSUST (or open it within a minute after a restart, while the server is still waking up).
- [ ] Within about 3 seconds the last numbers show with a bar **Offline, last updated hh:mm** (the time of the last good answer), not a spinner and not an empty app.
- [ ] Try to add a payment: it is refused with "You're offline: these are your last saved numbers..." and nothing changes.
2. Turn Airplane mode off and wait up to 15 seconds (or leave the app and come back).
- [ ] The offline bar goes away and the numbers are the server's again. Adding a payment works.

## 6. Things that must not happen

- [ ] No data from another phone ever shows up (try on a second iPhone with its own TestFlight install: each keeps its own data).
- [ ] After a restore, nothing is counted twice: the same number of payments as before the wipe.
- [ ] The widget keeps showing its last numbers while the server sleeps (it may show "set your budget" right after a wipe until SSUST is opened once).

If a step fails, note the time, the step and what the screen showed. Do not send screenshots of the data to anyone you would not show your spending to.
