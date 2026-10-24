import Foundation
import MeridianCore
import XCTest

final class MeridianCoreTests: XCTestCase {
    func testUrlPolicyAllowsOnlySiteHttpsPages() {
        let policy = UrlPolicy(siteURL: "https://sauravprivatelimited369-byte.github.io/Engine_Verse/")
        XCTAssertEqual(policy.home, "https://sauravprivatelimited369-byte.github.io/Engine_Verse/")
        XCTAssertEqual(policy.decide("https://sauravprivatelimited369-byte.github.io/Engine_Verse/"), .loadInApp)
        XCTAssertEqual(policy.decide("https://sauravprivatelimited369-byte.github.io/Engine_Verse/topics/arrays/"), .loadInApp)
        XCTAssertEqual(policy.decide("https://sauravprivatelimited369-byte.github.io/Engine_Verse"), .loadInApp)

        // External web and mail links go to the system browser / mail client.
        XCTAssertEqual(policy.decide("https://github.com/sauravprivatelimited369-byte/Engine_Verse"), .openExternally)
        XCTAssertEqual(policy.decide("https://sauravprivatelimited369-byte.github.io/OtherRepo/"), .openExternally)
        XCTAssertEqual(policy.decide("http://sauravprivatelimited369-byte.github.io/Engine_Verse/"), .openExternally)
        XCTAssertEqual(policy.decide("https://sauravprivatelimited369-byte.github.io:8443/Engine_Verse/"), .openExternally)
        XCTAssertEqual(policy.decide("https://user@sauravprivatelimited369-byte.github.io/Engine_Verse/"), .openExternally)
        XCTAssertEqual(policy.decide("https://sauravprivatelimited369-byte.github.io/Engine_Verse/../Other/"), .openExternally)
        XCTAssertEqual(policy.decide("mailto:help@example.org"), .openExternally)

        // Dangerous schemes are blocked outright.
        XCTAssertEqual(policy.decide("javascript:alert(1)"), .block)
        XCTAssertEqual(policy.decide("file:///etc/passwd"), .block)
        XCTAssertEqual(policy.decide("data:text/html,<h1>x</h1>"), .block)
        XCTAssertEqual(policy.decide("intent://evil"), .block)
        XCTAssertEqual(policy.decide(""), .block)

        // pageURL sanitizes untrusted paths back to home.
        XCTAssertEqual(policy.pageURL("topics/arrays/"), "https://sauravprivatelimited369-byte.github.io/Engine_Verse/topics/arrays/")
        XCTAssertEqual(policy.pageURL("../secret"), policy.home)
        XCTAssertEqual(policy.pageURL("https://evil.example"), policy.home)
    }

    func testCatalogSearchAndBundledJson() throws {
        let subjects = [
            Subject(
                slug: "dsa",
                name: "Data Structures & Algorithms",
                code: "CS201",
                group: "Computer Science",
                description: "Trees, graphs and dynamic programming",
                topics: [
                    Topic(slug: "arrays", title: "Arrays and Dynamic Arrays", summary: "Contiguous memory", difficulty: "easy", minutes: 15, tags: ["c++", "memory"], reviewed: true)
                ]
            ),
            Subject(
                slug: "thermo",
                name: "Thermodynamics",
                code: "ME102",
                group: "Mechanical",
                description: "Laws of heat and work",
                topics: [
                    Topic(slug: "entropy", title: "Entropy", summary: "Second law", difficulty: "medium", minutes: 20, tags: ["heat"], reviewed: false)
                ]
            ),
        ]
        XCTAssertEqual(CatalogSearch.filter(subjects, query: "c++ arrays").map(\.slug), ["dsa"])
        XCTAssertEqual(CatalogSearch.filter(subjects, query: "entropy").map(\.slug), ["thermo"])
        XCTAssertEqual(CatalogSearch.filter(subjects, query: "", group: "Mechanical").map(\.slug), ["thermo"])

        // Verify the real generated Resources/catalog.json decodes cleanly.
        let repoAppleCatalog = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Resources/catalog.json")
        let data = try Data(contentsOf: repoAppleCatalog)
        let catalog = try Catalog.decode(from: data)
        XCTAssertGreaterThan(catalog.subjects.count, 80)
        XCTAssertGreaterThan(catalog.topicCount, 300)
    }

    func testPlannerRulesOrderAndClean() {
        var tasks: [PlannerTask] = []
        tasks = PlannerRules.add(tasks, rawTitle: "   ", dueDay: nil, id: "empty", now: 1)
        XCTAssertTrue(tasks.isEmpty)

        tasks = PlannerRules.add(tasks, rawTitle: "  Read   Ohm's Law  ", dueDay: 200, id: "t1", now: 10)
        tasks = PlannerRules.add(tasks, rawTitle: "Solve Two Sum", dueDay: 100, id: "t2", now: 20)
        tasks = PlannerRules.add(tasks, rawTitle: "Undated revision", dueDay: nil, id: "t3", now: 5)

        XCTAssertEqual(tasks[0].title, "Read Ohm's Law")
        XCTAssertEqual(PlannerRules.sorted(tasks).map(\.id), ["t2", "t1", "t3"])
        XCTAssertEqual(PlannerRules.nextUp(tasks)?.id, "t2")

        tasks = PlannerRules.toggle(tasks, id: "t2")
        XCTAssertEqual(PlannerRules.nextUp(tasks)?.id, "t1")
        XCTAssertEqual(PlannerRules.dueLabel(dueDay: 99, today: 100), "Overdue")
        XCTAssertEqual(PlannerRules.dueLabel(dueDay: 100, today: 100), "Due today")
        XCTAssertEqual(PlannerRules.dueLabel(dueDay: 101, today: 100), "Due tomorrow")
        XCTAssertEqual(PlannerRules.dueLabel(dueDay: 105, today: 100), "Due in 5 days")

        tasks = PlannerRules.clearDone(tasks)
        XCTAssertEqual(tasks.map(\.id), ["t1", "t3"])
    }

    func testStreakComputation() {
        XCTAssertEqual(Streak.compute(days: [], today: 100), Streak.Result(current: 0, longest: 0))
        XCTAssertEqual(Streak.compute(days: [98, 99, 100], today: 100), Streak.Result(current: 3, longest: 3))
        // Yesterday still keeps the streak alive before today's session.
        XCTAssertEqual(Streak.compute(days: [90, 91, 92, 93, 98, 99], today: 100), Streak.Result(current: 2, longest: 4))
        // Gap of 2+ days resets current to 0 while preserving longest.
        XCTAssertEqual(Streak.compute(days: [90, 91, 92, 97], today: 100), Streak.Result(current: 0, longest: 3))
    }

    func testAppStorePersistsAndValidatesSlugs() {
        let suiteName = "io.github.sauravprivatelimited369byte.engineverse.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let store = AppStore(defaults: defaults)
        store.toggleTopic("arrays")
        store.toggleTopic("../invalid")
        store.addTask(title: "Revise pointers", dueDay: nil)
        store.setTheme(.dark)

        XCTAssertEqual(store.completedTopics, ["arrays"])
        XCTAssertEqual(store.tasks.count, 1)
        XCTAssertEqual(store.themeMode, .dark)

        let reloaded = AppStore(defaults: defaults)
        XCTAssertEqual(reloaded.completedTopics, ["arrays"])
        XCTAssertEqual(reloaded.tasks.count, 1)
        XCTAssertEqual(reloaded.themeMode, .dark)

        reloaded.clearAll()
        XCTAssertTrue(reloaded.completedTopics.isEmpty)
        XCTAssertTrue(reloaded.tasks.isEmpty)
        XCTAssertEqual(reloaded.themeMode, .system)
    }
}
