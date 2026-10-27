import MeridianCore
import SwiftUI

enum AppSection: String, CaseIterable, Hashable, Identifiable {
    case home
    case learn
    case practice
    case playground
    case planner
    case portfolio
    case settings

    var id: String { rawValue }

    var label: String {
        switch self {
        case .home: return "Home"
        case .learn: return "Learn"
        case .practice: return "Practice"
        case .playground: return "Code"
        case .planner: return "Planner"
        case .portfolio: return "Record"
        case .settings: return "Settings"
        }
    }

    var systemImage: String {
        switch self {
        case .home: return "house"
        case .learn: return "book.closed"
        case .practice: return "checklist"
        case .playground: return "chevron.left.forwardslash.chevron.right"
        case .planner: return "calendar"
        case .portfolio: return "person.text.rectangle"
        case .settings: return "gearshape"
        }
    }
}

struct WebDestination: Identifiable, Equatable {
    let id = UUID()
    let path: String
}

struct RootView: View {
    @ObservedObject var store: AppStore
    let catalog: Catalog
    let library: LessonLibrary
    let policy: UrlPolicy

    @State private var selection: AppSection = .home
    @State private var webDestination: WebDestination?
    @Environment(\.colorScheme) private var scheme
    #if os(iOS)
    @Environment(\.horizontalSizeClass) private var sizeClass
    #endif

    private func openWeb(_ path: String) {
        webDestination = WebDestination(path: path)
    }

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        Group {
            #if os(macOS)
            splitLayout(palette: palette)
            #else
            if sizeClass == .regular {
                splitLayout(palette: palette)
            } else {
                compactTabs(palette: palette)
            }
            #endif
        }
        .tint(palette.primary)
        .sheet(item: $webDestination) { dest in
            WebViewerSheet(
                path: dest.path,
                policy: policy,
                onClose: { webDestination = nil },
                openCatalog: {
                    webDestination = nil
                    selection = .learn
                }
            )
            #if os(macOS)
            .frame(minWidth: 920, minHeight: 640)
            #endif
        }
    }

    private func splitLayout(palette: MeridianPalette) -> some View {
        let optionalSelection = Binding<AppSection?>(
            get: { selection },
            set: { if let next = $0 { selection = next } }
        )
        return NavigationSplitView {
            List(AppSection.allCases, selection: optionalSelection) { section in
                Label(section.label, systemImage: section.systemImage)
                    .tag(section)
            }
            .navigationTitle(AppConfig.appName)
            #if os(macOS)
            .navigationSplitViewColumnWidth(min: 200, ideal: 220, max: 260)
            #endif
        } detail: {
            detailContent(for: selection)
                .background(palette.background.ignoresSafeArea())
        }
    }

    private func compactTabs(palette: MeridianPalette) -> some View {
        TabView(selection: $selection) {
            ForEach([AppSection.home, .learn, .practice, .planner, .portfolio]) { section in
                detailContent(for: section)
                    .background(palette.background.ignoresSafeArea())
                    .tabItem {
                        Label(section.label, systemImage: section.systemImage)
                    }
                    .tag(section)
            }
        }
    }

    @ViewBuilder
    private func detailContent(for section: AppSection) -> some View {
        switch section {
        case .home:
            NavigationStack {
                HomeView(
                    store: store,
                    catalog: catalog,
                    library: library,
                    selectSection: { selection = $0 },
                    openWeb: openWeb
                )
            }
        case .learn:
            NavigationStack {
                LearnView(store: store, catalog: catalog, library: library, openWeb: openWeb)
            }
        case .practice:
            NavigationStack {
                PracticeView(
                    store: store,
                    catalog: catalog,
                    library: library,
                    topicFilter: nil,
                    openWeb: openWeb
                )
            }
        case .playground:
            NavigationStack {
                PlaygroundView(openWeb: openWeb)
            }
        case .planner:
            NavigationStack {
                PlannerView(store: store)
            }
        case .portfolio:
            NavigationStack {
                PortfolioView(store: store, catalog: catalog, library: library, openWeb: openWeb)
            }
        case .settings:
            NavigationStack {
                SettingsView(store: store, openWeb: openWeb)
            }
        }
    }
}
