import Foundation

public struct PlannerTask: Codable, Equatable, Hashable, Identifiable, Sendable {
    public let id: String
    public var title: String
    /// Epoch day the task is due, or nil for "no date".
    public var dueDay: Int64?
    public var done: Bool
    public let createdAt: Int64

    public init(id: String, title: String, dueDay: Int64?, done: Bool, createdAt: Int64) {
        self.id = id
        self.title = title
        self.dueDay = dueDay
        self.done = done
        self.createdAt = createdAt
    }
}

public enum PlannerRules {
    public static let maxTitle = 120
    public static let maxTasks = 200

    public static func cleanTitle(_ raw: String) -> String? {
        let collapsed = raw
            .components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
        guard !collapsed.isEmpty else { return nil }
        return String(collapsed.prefix(maxTitle))
    }

    public static func add(
        _ tasks: [PlannerTask],
        rawTitle: String,
        dueDay: Int64?,
        id: String = UUID().uuidString,
        now: Int64
    ) -> [PlannerTask] {
        guard let title = cleanTitle(rawTitle), tasks.count < maxTasks else { return tasks }
        return tasks + [PlannerTask(id: id, title: title, dueDay: dueDay, done: false, createdAt: now)]
    }

    public static func toggle(_ tasks: [PlannerTask], id: String) -> [PlannerTask] {
        tasks.map { task in
            guard task.id == id else { return task }
            var copy = task
            copy.done.toggle()
            return copy
        }
    }

    public static func remove(_ tasks: [PlannerTask], id: String) -> [PlannerTask] {
        tasks.filter { $0.id != id }
    }

    public static func clearDone(_ tasks: [PlannerTask]) -> [PlannerTask] {
        tasks.filter { !$0.done }
    }

    /// Open tasks first (soonest due, undated last), then finished ones, newest first.
    public static func sorted(_ tasks: [PlannerTask]) -> [PlannerTask] {
        let open = tasks
            .filter { !$0.done }
            .sorted { lhs, rhs in
                let ld = lhs.dueDay ?? Int64.max
                let rd = rhs.dueDay ?? Int64.max
                if ld != rd { return ld < rd }
                return lhs.createdAt < rhs.createdAt
            }
        let done = tasks
            .filter { $0.done }
            .sorted { $0.createdAt > $1.createdAt }
        return open + done
    }

    public static func nextUp(_ tasks: [PlannerTask]) -> PlannerTask? {
        sorted(tasks).first { !$0.done }
    }

    public static func dueLabel(dueDay: Int64?, today: Int64) -> String? {
        guard let dueDay else { return nil }
        if dueDay < today { return "Overdue" }
        if dueDay == today { return "Due today" }
        if dueDay == today + 1 { return "Due tomorrow" }
        return "Due in \(dueDay - today) days"
    }
}
