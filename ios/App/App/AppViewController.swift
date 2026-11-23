// The app's web view with one extra message channel, "ssustWidget": the web app sends this phone's
// SSUST id, which goes into the App Group shared with the home screen widget (so nothing has to be
// pasted), and the widget is asked to refresh because the numbers changed.

import Capacitor
import UIKit
import WebKit
import WidgetKit

private let appGroup = "group.com.adamattar.ssust"

final class WidgetMessages: NSObject, WKScriptMessageHandler {
    private var lastReload = Date.distantPast

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any],
              let device = body["device"] as? String,
              device.count == 32,
              device.allSatisfy({ $0.isHexDigit && !$0.isUppercase }) else {
            return
        }
        UserDefaults(suiteName: appGroup)?.set(device, forKey: "device")
        let now = Date()
        if now.timeIntervalSince(lastReload) > 2 {
            lastReload = now
            WidgetCenter.shared.reloadAllTimelines()
        }
    }
}

class AppViewController: CAPBridgeViewController {
    private let widgetMessages = WidgetMessages()

    override open func capacitorDidLoad() {
        super.capacitorDidLoad()
        webView?.configuration.userContentController.add(widgetMessages, name: "ssustWidget")
    }
}
