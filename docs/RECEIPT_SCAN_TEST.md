# Receipt scan on a real iPhone: manual checklist

In the iPhone app, receipts are read on the phone with Apple's on-device text recognition (`ios/App/App/ReceiptScanner.swift`). No photo leaves the phone: only the extracted text goes to `POST /api/receipt/parse`, which finds the total. This part cannot be tested on Windows or in CI, so run this list on a real iPhone after each TestFlight build that changes it.

## Before you start

- Install the latest build from TestFlight and open SSUST once (it needs the hosted server, so wait for Today to load).
- Set a weekly budget so Add payment can save.
- Have the receipts below on hand. Use real ones where you can; write down what each one really says before you scan.

For each case, note: the amount filled in, the line shown under the button ("Line used: ..."), whether it says **best guess, check it**, and the fund. Nothing must ever be saved until you tap Save.

## 1. Supermarket receipt (Park n Shop style) with 小計 and a card line

1. Today > **Scan a receipt**. The scan screen opens (not the photo picker).
2. Hold the phone over the receipt until it frames it, take the shot, tap **Save** (or **Keep Scan**, then **Save**).
- [ ] Add payment opens with the amount paid by card (the VISA / MASTER / Octopus line), not an item price.
- [ ] If the receipt has a TOTAL line, the banner says "Read from receipt: check it". If it only has 小計 and the card line with the same amount, it is a sure total too.
- [ ] Chinese labels (小計, 合計, 找續) show up correctly under "What the reader saw" when you force a failure (cover the total with a finger).

## 2. Restaurant receipt with "Amount" and "$1,032.0"

1. Add payment > **Scan receipt**, scan the receipt.
- [ ] The amount is HK$1,032.00 and the line used reads like `Amount $1,032.0` (the label and the price on one line even if the price is printed far to the right).
- [ ] The service charge line or the subtotal is not taken instead.

## 3. A crumpled or curved receipt

1. Crumple a receipt, open it again without flattening it, scan it in normal room light.
- [ ] The scan screen straightens the page.
- [ ] The total is read, or the banner says **best guess, check it** with a sensible line, or it shows the retake hint ("No prices were read. Retake the photo flat...") with **What the reader saw** under it. It must never fill in a made-up amount.

## 4. Cash receipt with change

1. Scan a receipt paid in cash, with lines like `CASH 100.00` and `CHANGE 12.50` (or 找續).
- [ ] The amount is the total (87.50 in this example), never the cash given (100.00) or the change.

## 5. Photo picked from the library

1. Take a normal photo of a receipt with the Camera app first (portrait, a bit tilted).
2. Add payment > **From photos**, pick that photo.
- [ ] It is read the same way (no "Loading the offline reader" message: the phone reads it).
- [ ] A screenshot of a receipt works too.
- [ ] Cancel the picker: nothing changes, the form stays as it was.

## 6. Camera permission denied

1. iPhone Settings > SSUST > turn **Camera** off (or answer "Don't Allow" on the first scan).
2. Today > **Scan a receipt**.
- [ ] No crash and no black screen: Add payment shows "Camera access is off. Allow it in Settings > SSUST > Camera, or use From photos."
- [ ] **From photos** still works.
- [ ] Turn Camera back on, scan again: the scan screen opens.

## Also check

- [ ] Cancel on the scan screen: back to Add payment, no error message, nothing filled in.
- [ ] Scan a receipt with two pages (scan both): the total from the second page is found.
- [ ] Airplane mode: the scan screen still opens and reads the receipt, then Add payment says "Could not read this image. Type the amount in." (the server that finds the total cannot be reached) and nothing is filled in.
- [ ] The home screen widget still says it is linked (Settings > Apple Pay and widget) after scanning.
- [ ] The web version (any browser) still reads receipts with its offline reader, unchanged.

If a receipt is read wrong, keep the photo and copy the text under **What the reader saw** so the rules in `backend/ssust/receipt.py` can be checked against it.
