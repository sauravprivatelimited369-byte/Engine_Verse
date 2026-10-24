import Foundation

/// Study streaks over local epoch days (days since 1970-01-01 in local time).
public enum Streak {
    public struct Result: Equatable, Sendable {
        public let current: Int
        public let longest: Int

        public init(current: Int, longest: Int) {
            self.current = current
            self.longest = longest
        }
    }

    private static let daySeconds: Int64 = 86_400

    public static func today(now: Date = Date(), timeZone: TimeZone = .current) -> Int64 {
        let epochSeconds = Int64(floor(now.timeIntervalSince1970))
        let offset = Int64(timeZone.secondsFromGMT(for: now))
        let local = epochSeconds + offset
        return local >= 0 ? (local / daySeconds) : ((local - daySeconds + 1) / daySeconds)
    }

    public static func epochDay(for date: Date, timeZone: TimeZone = .current) -> Int64 {
        today(now: date, timeZone: timeZone)
    }

    /// Counts back from today, or from yesterday when today has no activity yet.
    public static func compute(days: Set<Int64>, today: Int64) -> Result {
        guard !days.isEmpty else { return Result(current: 0, longest: 0) }
        let ordered = days.sorted()
        var longest = 0
        var run = 0
        var previous: Int64?
        for day in ordered {
            if let prev = previous, day == prev + 1 {
                run += 1
            } else {
                run = 1
            }
            if run > longest { longest = run }
            previous = day
        }

        var cursor: Int64
        if days.contains(today) {
            cursor = today
        } else if days.contains(today - 1) {
            cursor = today - 1
        } else {
            return Result(current: 0, longest: longest)
        }

        var current = 0
        while days.contains(cursor) {
            current += 1
            cursor -= 1
        }
        return Result(current: current, longest: longest)
    }
}
