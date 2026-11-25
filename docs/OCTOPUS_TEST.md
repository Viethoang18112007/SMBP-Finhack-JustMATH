# Octopus taps on a real iPhone: manual checklist

Octopus in Apple Wallet does start the Shortcuts automation ("When I tap any card in Wallet"), but iOS does not give the automation the amount of a transit card tap. SSUST keeps such a tap in **To review** as "Octopus tap at hh:mm | amount?" and asks you for the amount. Bank cards in Apple Pay still send the amount by themselves.

Settings > **Apple Pay and widget** shows, under "Last Apple Pay message", which fields the last message carried, for example `Received: card yes (Octopus), amount no, merchant no`. Only the field names and the card name are kept, never the amount or the merchant.

This needs a real iPhone, an Octopus card in Wallet and a real payment. It cannot be tested on Windows or in CI.

## Before you start

- Push the branch, then Render > `ssust-api` > **Manual Deploy** > Deploy latest commit. Wait until the deploy is live.
- Start a new Codemagic build (`ios-testflight`) and install it from TestFlight.
- Open SSUST, set a weekly budget if there is none, and note **Left to spend today**.
- The Apple Pay automation from Settings > **Apple Pay and widget** is set up, with your Octopus card and a bank card selected, **Run Immediately** on.

## 1. One Octopus tap

1. Pay something small with the Octopus card in Wallet (a drink at a convenience store, or a bus or MTR ride).
2. Open SSUST > Settings > **Apple Pay and widget**.
- [ ] The line says **Tap received without amount: open SSUST to add it.** (not "Test run: the link works").
- [ ] Write down the **Received:** line exactly (card yes/no and its name, amount yes/no, merchant yes/no). This is what iOS really sends for Octopus.

## 2. Add the amount in To review

1. Open Today.
- [ ] **To review** shows **Octopus tap at hh:mm** (the time of the payment, Hong Kong time) with **amount?**.
- [ ] It has the amount field, the quick chips (HK$20, 35, 50, 80), a fund already picked with its reason, **Confirm** and **Dismiss**.
2. Press **Confirm** with the field empty.
- [ ] It says to enter the amount you paid. Nothing is saved.
3. Type the real amount from the receipt or the Octopus balance in Wallet, check the fund, press **Confirm**.
- [ ] The item leaves To review and the payment shows in today's payments with that amount.
- [ ] **Left to spend today** went down by exactly that amount (for Main meals or Snacks).
4. Optional: type an amount ten times too high (for example 480 for a HK$48 meal in Main meals).
- [ ] A **Typo?** line appears and the button becomes **Confirm HK$480 anyway**. Fix the amount instead.

## 3. Two quick fires for one tap

iOS can run the automation twice for one tap (once when the card is picked, once at payment).

1. Tap the Octopus card twice within a minute (or pay once and watch for two Shortcuts notifications).
2. Open Today.
- [ ] Only **one** Octopus item is in To review for those taps.
3. Dismiss it.
- [ ] It leaves To review and nothing is saved (today's payments and Left to spend today unchanged).

## 4. A bank card still works by itself

1. Pay a small amount with a bank card in Apple Pay.
2. Open Settings > **Apple Pay and widget**.
- [ ] The line says **Received HK$X from (merchant)**, and the Received line says amount yes.
3. Open Today.
- [ ] To review shows the amount and the merchant already filled in (no amount field). **Confirm** saves it as before.

## 5. The play button is still a test run

1. In the Shortcuts app, open the automation and tap **▶**.
- [ ] Settings says **Test run: the link works**, and the Received line says card no, amount no, merchant no.
- [ ] Nothing new is in To review.

## What to report back

- The **Received:** line from step 1 (what iOS sends for Octopus).
- Whether step 3 gave one item or two.
- Any step that did not match.

Known gap: if iOS sends no card, no amount and no merchant for an Octopus tap, the server cannot tell it apart from the play button test, and it shows "Test run: the link works". The Received line from step 1 tells us whether that happens.
