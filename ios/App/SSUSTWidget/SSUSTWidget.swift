// SSUST home screen widget: what is left to spend today, the logging streak and the payments waiting
// for review. It asks the SSUST server (GET /api/widget) with this phone's code, pasted once in the
// widget's settings (hold the widget > Edit Widget > Phone code). The app shows the code in
// Settings > Apple Pay and widget. Money comes from the server as integer cents plus its HK$ text,
// so the widget never formats or computes money. The last good answer is kept for when the server sleeps.

import AppIntents
import SwiftUI
import WidgetKit

private let apiBase = "https://ssust-api.onrender.com"
private let cacheKey = "ssust.widget.last"

struct PhoneCodeIntent: WidgetConfigurationIntent {
    static let title: LocalizedStringResource = "SSUST"
    static let description = IntentDescription("Shows what is left to spend today.")

    @Parameter(title: "Phone code")
    var code: String?

    init() {}
}

struct Summary: Codable {
    let ready: Bool
    let left: Int
    let leftText: String
    let over: Bool
    let streak: Int
    let shape: String
    let toReview: Int
}

struct SSUSTEntry: TimelineEntry {
    let date: Date
    let summary: Summary?
    let message: String
    let stale: Bool

    static let sample = SSUSTEntry(
        date: Date(),
        summary: Summary(ready: true, left: 8229, leftText: "HK$82.29", over: false, streak: 3, shape: "star", toReview: 1),
        message: "",
        stale: false)
}

struct Provider: AppIntentTimelineProvider {
    func placeholder(in context: Context) -> SSUSTEntry {
        SSUSTEntry.sample
    }

    func snapshot(for configuration: PhoneCodeIntent, in context: Context) async -> SSUSTEntry {
        if context.isPreview {
            return SSUSTEntry.sample
        }
        return await load(configuration.code)
    }

    func timeline(for configuration: PhoneCodeIntent, in context: Context) async -> Timeline<SSUSTEntry> {
        let entry = await load(configuration.code)
        let next = Date().addingTimeInterval(30 * 60)
        return Timeline(entries: [entry], policy: .after(next))
    }

    private func load(_ raw: String?) async -> SSUSTEntry {
        let code = (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard code.count == 32, code.allSatisfy({ $0.isHexDigit }) else {
            return SSUSTEntry(date: Date(), summary: nil,
                              message: "Hold this widget, Edit Widget, and paste your phone code from SSUST Settings.",
                              stale: false)
        }
        guard let url = URL(string: apiBase + "/api/widget") else {
            return cached(code)
        }
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 20)
        request.setValue(code, forHTTPHeaderField: "X-SSUST-Device")
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                return cached(code)
            }
            let summary = try JSONDecoder().decode(Summary.self, from: data)
            UserDefaults.standard.set(data, forKey: cacheKey + "." + code)
            return SSUSTEntry(date: Date(), summary: summary, message: "", stale: false)
        } catch {
            return cached(code)
        }
    }

    private func cached(_ code: String) -> SSUSTEntry {
        if let data = UserDefaults.standard.data(forKey: cacheKey + "." + code),
           let summary = try? JSONDecoder().decode(Summary.self, from: data) {
            return SSUSTEntry(date: Date(), summary: summary, message: "", stale: true)
        }
        return SSUSTEntry(date: Date(), summary: nil, message: "Server asleep. Open SSUST, then check again.", stale: false)
    }
}

private func symbol(for shape: String) -> String {
    switch shape {
    case "star": return "star.fill"
    case "diamond": return "diamond.fill"
    case "hexagon": return "hexagon.fill"
    case "crown": return "crown.fill"
    default: return "square.fill"
    }
}

struct SSUSTWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: SSUSTEntry

    var body: some View {
        content
            .containerBackground(.fill.tertiary, for: .widget)
    }

    @ViewBuilder
    private var content: some View {
        if let summary = entry.summary {
            if summary.ready {
                budget(summary)
            } else {
                note("Set your weekly budget in SSUST.")
            }
        } else {
            note(entry.message)
        }
    }

    private func budget(_ summary: Summary) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if family != .accessoryRectangular {
                Text("SSUST")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
            }
            Text(summary.leftText)
                .font(family == .accessoryRectangular ? .headline : .title.bold())
                .foregroundStyle(summary.over ? Color.red : Color.primary)
                .minimumScaleFactor(0.6)
                .lineLimit(1)
            Text(summary.over ? "over today" : "left today")
                .font(.caption)
                .foregroundStyle(.secondary)
            if family != .accessoryRectangular {
                Spacer(minLength: 0)
                HStack(spacing: 8) {
                    if summary.streak > 0 {
                        Label("\(summary.streak)", systemImage: symbol(for: summary.shape))
                            .font(.caption.bold())
                    }
                    if summary.toReview > 0 {
                        Text("\(summary.toReview) to review")
                            .font(.caption)
                    }
                }
                if entry.stale {
                    Text("Last known")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func note(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("SSUST")
                .font(.caption.bold())
            Text(text)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

struct SSUSTWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "SSUSTWidget", intent: PhoneCodeIntent.self, provider: Provider()) { entry in
            SSUSTWidgetView(entry: entry)
        }
        .configurationDisplayName("SSUST")
        .description("What is left to spend today.")
        .supportedFamilies([.systemSmall, .systemMedium, .accessoryRectangular])
    }
}

@main
struct SSUSTWidgets: WidgetBundle {
    var body: some Widget {
        SSUSTWidget()
    }
}
