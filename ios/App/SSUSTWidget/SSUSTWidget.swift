// SSUST home screen widget: what is left to spend today (a ring against today's allowance), every
// fund, today's last payments, the logging streak and the payments waiting for review.
// It asks the SSUST server (GET /api/widget) with this phone's id. The app puts that id in the App
// Group it shares with the widget (AppViewController), so nothing has to be pasted; the "Phone code"
// setting is only a fallback. Money comes from the server as integer cents plus its HK$ text, so the
// widget never formats or computes money. The last good answer is kept for when the server sleeps.
//
// Quick type (QuickTypeWidget): a bar shaped like a search field. A widget cannot take typed text,
// so a tap opens the app through ssust://quick on its Quick type sheet, the field focused.

import AppIntents
import SwiftUI
import WidgetKit

private let apiBase = "https://ssust-api.onrender.com"
private let cacheKey = "ssust.widget.last"
private let brand = Color(red: 0.12, green: 0.31, blue: 0.55)
private let quickURL = URL(string: "ssust://quick")!

struct PhoneCodeIntent: WidgetConfigurationIntent {
    static let title: LocalizedStringResource = "UniVault"
    static let description = IntentDescription("Shows what is left to spend today.")

    @Parameter(title: "Phone code (only if the widget asks)")
    var code: String?

    init() {}
}

struct FundLine: Codable {
    let fund: String
    let name: String
    let left: Int
    let leftText: String
    let allocationText: String
    let level: Int
}

struct PaymentLine: Codable {
    let label: String
    let amountText: String
    let fund: String
}

struct Summary: Codable {
    let ready: Bool
    let left: Int
    let leftText: String
    let over: Bool
    let allowanceText: String?
    let spentText: String?
    let spentRatio: Int?
    let tomorrowText: String?
    let daysLeft: Int?
    let funds: [FundLine]?
    let payments: [PaymentLine]?
    let streak: Int
    let shape: String
    let toReview: Int

    // Share of today's allowance still there, 0...1, for the ring.
    var leftShare: Double {
        if over { return 0 }
        let used = Double(min(max(spentRatio ?? 0, 0), 1000)) / 1000
        return 1 - used
    }
}

struct SSUSTEntry: TimelineEntry {
    let date: Date
    let summary: Summary?
    let message: String
    let stale: Bool

    static let sample = SSUSTEntry(
        date: Date(),
        summary: Summary(
            ready: true, left: 2229, leftText: "HK$22.29", over: false,
            allowanceText: "HK$64.29", spentText: "HK$42", spentRatio: 653, tomorrowText: "HK$64.29", daysLeft: 5,
            funds: [
                FundLine(fund: "main", name: "Main meals", left: 35800, leftText: "HK$358", allocationText: "HK$400", level: 895),
                FundLine(fund: "snack", name: "Snacks", left: 3200, leftText: "HK$32", allocationText: "HK$50", level: 640),
                FundLine(fund: "fixed", name: "Fixed Bills", left: 15000, leftText: "HK$150", allocationText: "HK$150", level: 1000),
                FundLine(fund: "experience", name: "Experience", left: 10000, leftText: "HK$100", allocationText: "HK$100", level: 1000),
                FundLine(fund: "development", name: "Development", left: 10000, leftText: "HK$100", allocationText: "HK$100", level: 1000),
                FundLine(fund: "savings", name: "Long-term Savings", left: 20000, leftText: "HK$200", allocationText: "HK$200", level: 1000),
            ],
            payments: [PaymentLine(label: "Lunch canteen", amountText: "HK$42", fund: "main")],
            streak: 3, shape: "star", toReview: 1),
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

    // The app's own id first (App Group), else the code typed in the widget's settings.
    private func phoneCode(_ configured: String?) -> String {
        let shared = UserDefaults(suiteName: "group.com.adamattar.ssust")?.string(forKey: "device") ?? ""
        let raw = shared.isEmpty ? (configured ?? "") : shared
        return raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private func load(_ configured: String?) async -> SSUSTEntry {
        let code = phoneCode(configured)
        guard code.count == 32, code.allSatisfy({ $0.isHexDigit }) else {
            return SSUSTEntry(date: Date(), summary: nil, message: "Open UniVault once, then come back here.", stale: false)
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
        return SSUSTEntry(date: Date(), summary: nil, message: "Server asleep. Open UniVault, then check again.", stale: false)
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

// The same fund colours as the app.
private func fundColor(_ fund: String) -> Color {
    switch fund {
    case "main": return brand
    case "snack": return Color(red: 0.85, green: 0.6, blue: 0.1)
    case "fixed": return Color(red: 0.36, green: 0.45, blue: 0.58)
    case "experience": return Color(red: 0.55, green: 0.36, blue: 0.82)
    case "development": return Color(red: 0.1, green: 0.58, blue: 0.58)
    default: return Color(red: 0.15, green: 0.55, blue: 0.33)
    }
}

struct TodayRing: View {
    let summary: Summary
    let lineWidth: CGFloat

    var body: some View {
        ZStack {
            Circle()
                .stroke(Color.secondary.opacity(0.2), lineWidth: lineWidth)
            Circle()
                .trim(from: 0, to: CGFloat(summary.leftShare))
                .stroke(summary.over ? Color.red : brand, style: StrokeStyle(lineWidth: lineWidth, lineCap: .round))
                .rotationEffect(.degrees(-90))
            VStack(spacing: 0) {
                Text(summary.leftText)
                    .font(.system(.headline, design: .rounded).bold())
                    .foregroundStyle(summary.over ? Color.red : Color.primary)
                    .minimumScaleFactor(0.5)
                    .lineLimit(1)
                Text(summary.over ? "over today" : "left today")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding(lineWidth + 4)
        }
    }
}

struct FundBar: View {
    let fund: FundLine

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                Text(fund.name)
                    .font(.caption2)
                    .lineLimit(1)
                Spacer(minLength: 4)
                Text(fund.leftText)
                    .font(.caption2.bold())
                    .monospacedDigit()
                    .lineLimit(1)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.secondary.opacity(0.2))
                    Capsule()
                        .fill(fundColor(fund.fund))
                        .frame(width: geo.size.width * CGFloat(min(max(fund.level, 0), 1000)) / 1000)
                }
            }
            .frame(height: 5)
        }
    }
}

struct StreakBadge: View {
    let summary: Summary

    var body: some View {
        HStack(spacing: 6) {
            if summary.streak > 0 {
                Label("\(summary.streak)", systemImage: symbol(for: summary.shape))
                    .font(.caption2.bold())
                    .foregroundStyle(brand)
            }
            if summary.toReview > 0 {
                Text("\(summary.toReview) to review")
                    .font(.caption2.bold())
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Capsule().fill(Color.orange.opacity(0.2)))
            }
        }
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
                switch family {
                case .accessoryCircular:
                    circular(summary)
                case .accessoryRectangular:
                    rectangular(summary)
                case .systemMedium:
                    medium(summary)
                case .systemLarge:
                    large(summary)
                default:
                    small(summary)
                }
            } else {
                note("Set your weekly budget in UniVault.")
            }
        } else {
            note(entry.message)
        }
    }

    private func header(_ summary: Summary) -> some View {
        HStack(spacing: 4) {
            Text("UniVault")
                .font(.caption.bold())
                .foregroundStyle(brand)
            Spacer(minLength: 4)
            StreakBadge(summary: summary)
        }
    }

    private func spentLine(_ summary: Summary) -> some View {
        Group {
            if let spent = summary.spentText, let allowance = summary.allowanceText {
                Text("Spent \(spent) of \(allowance)")
            } else {
                Text(" ")
            }
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
        .lineLimit(1)
        .minimumScaleFactor(0.7)
    }

    private func staleLine() -> some View {
        Group {
            if entry.stale {
                Text("Last known")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func small(_ summary: Summary) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            header(summary)
            TodayRing(summary: summary, lineWidth: 7)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            spentLine(summary)
            staleLine()
        }
    }

    private func spendingFunds(_ summary: Summary) -> [FundLine] {
        (summary.funds ?? []).filter { $0.fund != "savings" && $0.fund != "fixed" }
    }

    private func medium(_ summary: Summary) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("UniVault")
                    .font(.caption.bold())
                    .foregroundStyle(brand)
                TodayRing(summary: summary, lineWidth: 7)
                spentLine(summary)
            }
            .frame(maxWidth: 130)
            VStack(alignment: .leading, spacing: 6) {
                StreakBadge(summary: summary)
                ForEach(Array(spendingFunds(summary).enumerated()), id: \.offset) { _, fund in
                    FundBar(fund: fund)
                }
                Spacer(minLength: 0)
                staleLine()
            }
        }
    }

    private func large(_ summary: Summary) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("UniVault")
                    .font(.headline)
                    .foregroundStyle(brand)
                Text(entry.date, format: .dateTime.weekday(.abbreviated).day().month())
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer(minLength: 4)
                StreakBadge(summary: summary)
            }
            HStack(spacing: 14) {
                TodayRing(summary: summary, lineWidth: 8)
                    .frame(width: 110, height: 110)
                VStack(alignment: .leading, spacing: 4) {
                    spentLine(summary)
                    if let tomorrow = summary.tomorrowText {
                        Text("Tomorrow \(tomorrow)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    if let days = summary.daysLeft {
                        Text(days == 1 ? "Last day of the week" : "\(days) days left this week")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    staleLine()
                }
            }
            ForEach(Array((summary.funds ?? []).enumerated()), id: \.offset) { _, fund in
                FundBar(fund: fund)
            }
            Divider()
            Text("Today")
                .font(.caption.bold())
            if let payments = summary.payments, !payments.isEmpty {
                ForEach(Array(payments.enumerated()), id: \.offset) { _, payment in
                    HStack(spacing: 6) {
                        Circle()
                            .fill(fundColor(payment.fund))
                            .frame(width: 6, height: 6)
                        Text(payment.label)
                            .font(.caption2)
                            .lineLimit(1)
                        Spacer(minLength: 4)
                        Text(payment.amountText)
                            .font(.caption2.bold())
                            .monospacedDigit()
                    }
                }
            } else {
                Text("Nothing yet today.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
    }

    private func circular(_ summary: Summary) -> some View {
        Gauge(value: summary.leftShare) {
            Text("UniVault")
        } currentValueLabel: {
            Text(summary.leftText)
                .minimumScaleFactor(0.4)
        }
        .gaugeStyle(.accessoryCircularCapacity)
    }

    private func rectangular(_ summary: Summary) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text("UniVault")
                .font(.caption2.bold())
            Text(summary.over ? "\(summary.leftText) over today" : "\(summary.leftText) left today")
                .font(.headline)
                .minimumScaleFactor(0.6)
                .lineLimit(1)
            if summary.toReview > 0 {
                Text("\(summary.toReview) to review")
                    .font(.caption2)
            } else if let spent = summary.spentText {
                Text("Spent \(spent)")
                    .font(.caption2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func note(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("UniVault")
                .font(.caption.bold())
                .foregroundStyle(brand)
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
        .configurationDisplayName("UniVault")
        .description("What is left to spend today, your funds and today's payments.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge, .accessoryCircular, .accessoryRectangular])
    }
}

// The Quick type bar: what is left today above a field with the same example as the web widget.
struct QuickTypeView: View {
    @Environment(\.widgetFamily) private var family
    let entry: SSUSTEntry

    var body: some View {
        content
            .widgetURL(quickURL)
            .containerBackground(.fill.tertiary, for: .widget)
    }

    private var leftLine: String {
        guard let summary = entry.summary, summary.ready else { return "Quick add" }
        return summary.over ? "\(summary.leftText) over today" : "\(summary.leftText) left today"
    }

    @ViewBuilder
    private var content: some View {
        if family == .accessoryRectangular {
            VStack(alignment: .leading, spacing: 1) {
                Text("UniVault")
                    .font(.caption2.bold())
                Label("Type a payment", systemImage: "keyboard")
                    .font(.headline)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Text(leftLine)
                    .font(.caption2)
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 4) {
                    Text("UniVault")
                        .font(.caption.bold())
                        .foregroundStyle(brand)
                    Spacer(minLength: 4)
                    Text(leftLine)
                        .font(.caption2.bold())
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                }
                HStack(spacing: 8) {
                    Image(systemName: "keyboard")
                        .foregroundStyle(.secondary)
                    Text("$50 KFC dinner")
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    Text("Go")
                        .font(.caption.bold())
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Capsule().fill(brand))
                }
                .padding(.leading, 12)
                .padding(.trailing, 6)
                .padding(.vertical, 6)
                .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Color.secondary.opacity(0.15)))
                Text("Tap to type a payment. Read by offline rules, not AI.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
        }
    }
}

struct QuickTypeWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "SSUSTQuickType", intent: PhoneCodeIntent.self, provider: Provider()) { entry in
            QuickTypeView(entry: entry)
        }
        .configurationDisplayName("Quick type")
        .description("A bar that opens UniVault ready to type a payment, like $50 KFC dinner.")
        .supportedFamilies([.systemMedium, .accessoryRectangular])
    }
}

@main
struct SSUSTWidgets: WidgetBundle {
    var body: some Widget {
        SSUSTWidget()
        QuickTypeWidget()
    }
}
