import MeridianCore
import SwiftUI

@main
struct MeridianAppleApp: App {
    @StateObject private var store = AppStore()
    @StateObject private var libraryStore = LibraryStore()
    private let catalog = Catalog.loadBundled()
    private let policy = UrlPolicy(siteURL: AppConfig.siteURL)

    var body: some Scene {
        WindowGroup {
            RootView(
                store: store,
                catalog: catalog,
                library: libraryStore.library,
                policy: policy
            )
            .preferredColorScheme(store.themeMode.preferredScheme)
            .task { libraryStore.loadIfNeeded() }
        }
        #if os(macOS)
        .defaultSize(width: 1120, height: 760)
        #endif
    }
}
