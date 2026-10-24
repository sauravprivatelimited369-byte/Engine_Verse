import Foundation

public struct Topic: Codable, Equatable, Hashable, Identifiable, Sendable {
    public var id: String { slug }
    public let slug: String
    public let title: String
    public let summary: String
    public let difficulty: String
    public let minutes: Int
    public let tags: [String]
    /// False for public drafts that have not completed editorial review.
    public let reviewed: Bool

    public init(
        slug: String,
        title: String,
        summary: String,
        difficulty: String,
        minutes: Int,
        tags: [String],
        reviewed: Bool
    ) {
        self.slug = slug
        self.title = title
        self.summary = summary
        self.difficulty = difficulty
        self.minutes = minutes
        self.tags = tags
        self.reviewed = reviewed
    }
}

public struct Subject: Codable, Equatable, Hashable, Identifiable, Sendable {
    public var id: String { slug }
    public let slug: String
    public let name: String
    public let code: String
    public let group: String
    public let description: String
    public let topics: [Topic]

    public init(
        slug: String,
        name: String,
        code: String,
        group: String,
        description: String,
        topics: [Topic]
    ) {
        self.slug = slug
        self.name = name
        self.code = code
        self.group = group
        self.description = description
        self.topics = topics
    }
}

private struct CatalogDocument: Decodable {
    let format: String
    let version: Int
    let site: String
    let subjects: [Subject]
}

public final class Catalog: Sendable {
    public static let empty = Catalog(subjects: [])

    public let subjects: [Subject]
    private let subjectIndex: [String: Subject]
    private let topicIndex: [String: (Subject, Topic)]

    public var topicCount: Int { topicIndex.count }

    public var groups: [String] {
        var seen = Set<String>()
        var ordered: [String] = []
        for subject in subjects {
            let g = subject.group.trimmingCharacters(in: .whitespacesAndNewlines)
            if !g.isEmpty && seen.insert(g).inserted {
                ordered.append(g)
            }
        }
        return ordered.sorted { lhs, rhs in
            if lhs == "First year" { return true }
            if rhs == "First year" { return false }
            return lhs.localizedCaseInsensitiveCompare(rhs) == .orderedAscending
        }
    }

    public init(subjects: [Subject]) {
        self.subjects = subjects
        var sIdx: [String: Subject] = [:]
        var tIdx: [String: (Subject, Topic)] = [:]
        for s in subjects {
            sIdx[s.slug] = s
            for t in s.topics {
                tIdx[t.slug] = (s, t)
            }
        }
        self.subjectIndex = sIdx
        self.topicIndex = tIdx
    }

    public func subject(_ slug: String) -> Subject? {
        subjectIndex[slug]
    }

    public func topic(_ slug: String) -> (Subject, Topic)? {
        topicIndex[slug]
    }

    public static func decode(from data: Data) throws -> Catalog {
        let doc = try JSONDecoder().decode(CatalogDocument.self, from: data)
        guard doc.version == 1,
              doc.format == "engineverse-apple-catalog" || doc.format == "engineverse-android-catalog"
        else {
            throw CocoaError(.coderReadCorrupt)
        }
        return Catalog(subjects: doc.subjects)
    }

    public static func loadBundled() -> Catalog {
        if let url = Bundle.main.url(forResource: "catalog", withExtension: "json"),
           let data = try? Data(contentsOf: url),
           let catalog = try? decode(from: data) {
            return catalog
        }
        // Fallback when launched directly via `swift run` from the apple/ directory.
        let cwdURL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources/catalog.json")
        if let data = try? Data(contentsOf: cwdURL),
           let catalog = try? decode(from: data) {
            return catalog
        }
        return .empty
    }
}

public enum CatalogSearch {
    public static func normalize(_ text: String) -> String {
        let lower = text.lowercased()
        var out = String.UnicodeScalarView()
        var previousSpace = true
        for scalar in lower.unicodeScalars {
            let v = scalar.value
            let allowed = (v >= 97 && v <= 122) || (v >= 48 && v <= 57) || v == 43 || v == 35
            if allowed {
                out.append(scalar)
                previousSpace = false
            } else if !previousSpace {
                out.append(" ")
                previousSpace = true
            }
        }
        return String(out).trimmingCharacters(in: .whitespaces)
    }

    /// Subjects whose name, code, group, description, topic titles or tags contain every query word.
    public static func filter(_ subjects: [Subject], query: String, group: String? = nil) -> [Subject] {
        let groupFiltered: [Subject]
        if let group, !group.isEmpty {
            groupFiltered = subjects.filter { $0.group == group }
        } else {
            groupFiltered = subjects
        }
        let words = normalize(query).split(separator: " ").map(String.init).filter { !$0.isEmpty }
        if words.isEmpty { return groupFiltered }

        return groupFiltered.filter { subject in
            var pieces: [String] = [subject.name, subject.code, subject.group, subject.description]
            for topic in subject.topics {
                pieces.append(topic.title)
                pieces.append(contentsOf: topic.tags)
            }
            let haystack = normalize(pieces.joined(separator: " "))
            return words.allSatisfy { haystack.contains($0) }
        }
    }
}
