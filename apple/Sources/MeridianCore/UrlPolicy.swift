import Foundation

/// Decides where a URL may open. Only pages of the Meridian website (one HTTPS
/// origin and its base path) load inside the app; ordinary web links go to the
/// user's browser; every other scheme (javascript:, file:, data:, about: ...)
/// is blocked so a page cannot reach into the device.
public final class UrlPolicy: Sendable {
    public enum Decision: Equatable, Sendable {
        case loadInApp
        case openExternally
        case block
    }

    private let host: String
    private let basePath: String
    public let home: String

    public init(siteURL: String = AppConfig.siteURL) {
        guard let comps = URLComponents(string: siteURL),
              let parsedHost = comps.host?.lowercased(),
              !parsedHost.isEmpty
        else {
            preconditionFailure("siteURL requires a valid host")
        }
        self.host = parsedHost
        let rawPath = comps.path.isEmpty ? "/" : comps.path
        self.basePath = rawPath.hasSuffix("/") ? rawPath : (rawPath + "/")
        self.home = "https://\(parsedHost)\(self.basePath)"
    }

    public func decide(_ rawURL: String) -> Decision {
        let trimmed = rawURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty,
              let comps = URLComponents(string: trimmed),
              let scheme = comps.scheme?.lowercased()
        else {
            return .block
        }
        switch scheme {
        case "https":
            return isSitePage(comps) ? .loadInApp : .openExternally
        case "http":
            guard let h = comps.host, !h.isEmpty else { return .block }
            return .openExternally
        case "mailto":
            return .openExternally
        default:
            return .block
        }
    }

    private func isSitePage(_ comps: URLComponents) -> Bool {
        guard comps.host?.lowercased() == host else { return false }
        if let port = comps.port, port != 443 { return false }
        if comps.user != nil || comps.password != nil { return false }
        let rawPath = comps.percentEncodedPath.isEmpty ? "/" : comps.percentEncodedPath
        if rawPath.contains("..") || rawPath.lowercased().contains("%2e%2e") {
            return false
        }
        let normalized = standardizePath(rawPath)
        let prefixWithoutTrailing = basePath == "/" ? "/" : String(basePath.dropLast())
        if basePath == "/" {
            return normalized.hasPrefix("/")
        }
        return normalized == prefixWithoutTrailing || normalized.hasPrefix(basePath)
    }

    private func standardizePath(_ path: String) -> String {
        var stack: [Substring] = []
        for part in path.split(separator: "/", omittingEmptySubsequences: true) {
            if part == "." { continue }
            if part == ".." {
                if !stack.isEmpty { stack.removeLast() }
                continue
            }
            stack.append(part)
        }
        let trailing = path.hasSuffix("/") && !stack.isEmpty ? "/" : ""
        return "/" + stack.joined(separator: "/") + trailing
    }

    /// Builds an absolute URL from a site-relative path such as `"topics/arrays/"`.
    /// Untrusted inputs fall back to `home`.
    public func pageURL(_ path: String) -> String {
        let clean = path.trimmingCharacters(in: .whitespacesAndNewlines)
            .drop(while: { $0 == "/" })
        let text = String(clean)
        guard !text.isEmpty else { return home }
        guard !text.contains(".."), Self.isSafeRelativePath(text) else { return home }
        return home + text
    }

    private static func isSafeRelativePath(_ value: String) -> Bool {
        for scalar in value.unicodeScalars {
            let v = scalar.value
            let ok = (v >= 65 && v <= 90)
                || (v >= 97 && v <= 122)
                || (v >= 48 && v <= 57)
                || v == 46 || v == 95 || v == 126 || v == 47 || v == 45
            if !ok { return false }
        }
        return true
    }
}
