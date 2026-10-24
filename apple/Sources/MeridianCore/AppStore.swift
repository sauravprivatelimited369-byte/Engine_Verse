import Combine
import Foundation

public enum ThemeMode: String, CaseIterable, Codable, Sendable {
    case system = "SYSTEM"
    case light = "LIGHT"
    case dark = "DARK"
}

/// Device-local study progress, streaks, planner tasks and theme preference.
/// No account, analytics or cloud upload — stored only in this app's UserDefaults.
public final class AppStore: ObservableObject {
    @Published public private(set) var completedTopics: [String]
    @Published public private(set) var activityDays: Set<Int64>
    @Published public private(set) var tasks: [PlannerTask]
    @Published public private(set) var themeMode: ThemeMode

    private let defaults: UserDefaults

    private enum Keys {
        static let completed = "completed_topics"
        static let days = "activity_days"
        static let tasks = "planner_tasks"
        static let theme = "theme"
    }

    public init(defaults: UserDefaults = UserDefaults(suiteName: "\(AppConfig.bundleIdentifier).store") ?? .standard) {
        self.defaults = defaults
        self.completedTopics = Self.readCompleted(from: defaults)
        self.activityDays = Self.readDays(from: defaults)
        self.tasks = Self.readTasks(from: defaults)
        self.themeMode = Self.readTheme(from: defaults)
    }

    public var streak: Streak.Result {
        Streak.compute(days: activityDays, today: Streak.today())
    }

    public func isCompleted(_ slug: String) -> Bool {
        completedTopics.contains(slug)
    }

    public func toggleTopic(_ slug: String) {
        guard Self.isValidSlug(slug) else { return }
        if let idx = completedTopics.firstIndex(of: slug) {
            completedTopics.remove(at: idx)
        } else {
            recordActivity()
            completedTopics.append(slug)
        }
        if let data = try? JSONEncoder().encode(completedTopics) {
            defaults.set(data, forKey: Keys.completed)
        }
    }

    public func recordActivity(today: Int64 = Streak.today()) {
        guard !activityDays.contains(today) else { return }
        activityDays = activityDays.union([today]).filter { $0 > today - 730 }
        let encoded = Array(activityDays).sorted()
        if let data = try? JSONEncoder().encode(encoded) {
            defaults.set(data, forKey: Keys.days)
        }
    }

    public func addTask(title: String, dueDay: Int64?) {
        let nowMs = Int64(Date().timeIntervalSince1970 * 1000.0)
        updateTasks(PlannerRules.add(tasks, rawTitle: title, dueDay: dueDay, now: nowMs))
    }

    public func toggleTask(_ id: String) {
        let before = tasks.first { $0.id == id }
        updateTasks(PlannerRules.toggle(tasks, id: id))
        if let before, !before.done {
            recordActivity()
        }
    }

    public func removeTask(_ id: String) {
        updateTasks(PlannerRules.remove(tasks, id: id))
    }

    public func clearDoneTasks() {
        updateTasks(PlannerRules.clearDone(tasks))
    }

    public func setTheme(_ mode: ThemeMode) {
        themeMode = mode
        defaults.set(mode.rawValue, forKey: Keys.theme)
    }

    public func clearAll() {
        defaults.removeObject(forKey: Keys.completed)
        defaults.removeObject(forKey: Keys.days)
        defaults.removeObject(forKey: Keys.tasks)
        defaults.removeObject(forKey: Keys.theme)
        completedTopics = []
        activityDays = []
        tasks = []
        themeMode = .system
    }

    public func summaryText(catalog: Catalog) -> String {
        let grouped = Dictionary(grouping: completedTopics.compactMap { catalog.topic($0) }, by: { $0.0.slug })
        let sortedGroups = grouped.values
            .compactMap { pairs -> (Subject, [Topic])? in
                guard let subject = pairs.first?.0 else { return nil }
                return (subject, pairs.map(\.1))
            }
            .sorted { $0.0.name.localizedCaseInsensitiveCompare($1.0.name) == .orderedAscending }
        let tasksDone = tasks.filter(\.done).count
        var out = "My Meridian study record (self-reported)\n"
        out += "\(completedTopics.count) topics across \(sortedGroups.count) subjects; "
        out += "best streak \(streak.longest) days; \(tasksDone) planner tasks finished.\n"
        for (subject, topics) in sortedGroups {
            out += "\n\(subject.name): " + topics.map(\.title).joined(separator: ", ")
        }
        return out
    }

    private func updateTasks(_ next: [PlannerTask]) {
        tasks = next
        if let data = try? JSONEncoder().encode(next) {
            defaults.set(data, forKey: Keys.tasks)
        }
    }

    private static func readCompleted(from defaults: UserDefaults) -> [String] {
        guard let data = defaults.data(forKey: Keys.completed),
              let raw = try? JSONDecoder().decode([String].self, from: data)
        else { return [] }
        var seen = Set<String>()
        return raw.filter { isValidSlug($0) && seen.insert($0).inserted }
    }

    private static func readDays(from defaults: UserDefaults) -> Set<Int64> {
        guard let data = defaults.data(forKey: Keys.days),
              let raw = try? JSONDecoder().decode([Int64].self, from: data)
        else { return [] }
        return Set(raw)
    }

    private static func readTasks(from defaults: UserDefaults) -> [PlannerTask] {
        guard let data = defaults.data(forKey: Keys.tasks),
              let raw = try? JSONDecoder().decode([PlannerTask].self, from: data)
        else { return [] }
        return Array(raw.compactMap { item -> PlannerTask? in
            guard let clean = PlannerRules.cleanTitle(item.title) else { return nil }
            let id = item.id.trimmingCharacters(in: .whitespacesAndNewlines)
            return PlannerTask(
                id: id.isEmpty ? UUID().uuidString : id,
                title: clean,
                dueDay: item.dueDay,
                done: item.done,
                createdAt: item.createdAt
            )
        }.prefix(PlannerRules.maxTasks))
    }

    private static func readTheme(from defaults: UserDefaults) -> ThemeMode {
        guard let raw = defaults.string(forKey: Keys.theme),
              let mode = ThemeMode(rawValue: raw)
        else { return .system }
        return mode
    }

    public static func isValidSlug(_ slug: String) -> Bool {
        guard !slug.isEmpty, slug.count <= 121 else { return false }
        guard let first = slug.unicodeScalars.first else { return false }
        let firstOk = (first.value >= 97 && first.value <= 122) || (first.value >= 48 && first.value <= 57)
        guard firstOk else { return false }
        for scalar in slug.unicodeScalars {
            let v = scalar.value
            let ok = (v >= 97 && v <= 122) || (v >= 48 && v <= 57) || v == 45
            if !ok { return false }
        }
        return true
    }
}
