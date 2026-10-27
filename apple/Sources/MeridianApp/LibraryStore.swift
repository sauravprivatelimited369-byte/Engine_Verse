import Combine
import Foundation
import MeridianCore

/// Loads the bundled lesson library off the main thread. It carries every topic
/// at four note depths plus the practice bank, so the first screen should not
/// wait for it: the app is usable while it decodes.
@MainActor
final class LibraryStore: ObservableObject {
    @Published private(set) var library: LessonLibrary = .empty
    private var started = false

    func loadIfNeeded() {
        guard !started else { return }
        started = true
        Task.detached(priority: .userInitiated) { [weak self] in
            let loaded = LessonLibrary.loadBundled()
            await self?.apply(loaded)
        }
    }

    private func apply(_ loaded: LessonLibrary) {
        library = loaded
    }
}
