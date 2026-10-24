import MeridianCore
import SwiftUI

struct SettingsView: View {
    @ObservedObject var store: AppStore
    let openWeb: (String) -> Void

    @State private var confirmDelete = false
    @Environment(\.colorScheme) private var scheme
    @Environment(\.openURL) private var openURL

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Appearance")
                        .font(.headline)
                        .foregroundStyle(palette.ink)
                    Picker("Theme", selection: Binding(
                        get: { store.themeMode },
                        set: { store.setTheme($0) }
                    )) {
                        Text("Follow system").tag(ThemeMode.system)
                        Text("Light").tag(ThemeMode.light)
                        Text("Dark").tag(ThemeMode.dark)
                    }
                    .pickerStyle(.segmented)
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
                )

                VStack(alignment: .leading, spacing: 10) {
                    Text("Your data")
                        .font(.headline)
                        .foregroundStyle(palette.ink)
                    Text("There is no account. Completed topics, your streak and planner tasks are stored only inside this app on this device. Nothing is uploaded and there is no analytics. Pages you open from the website load over HTTPS from GitHub Pages; that site keeps its own progress in its own storage.")
                        .font(.subheadline)
                        .foregroundStyle(palette.mutedInk)
                    Button("Delete all app data", role: .destructive) {
                        confirmDelete = true
                    }
                    .buttonStyle(.bordered)
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
                )

                VStack(alignment: .leading, spacing: 10) {
                    Text("About")
                        .font(.headline)
                        .foregroundStyle(palette.ink)
                    Text("\(AppConfig.appName) \(AppConfig.version)")
                        .font(.body.weight(.medium))
                        .foregroundStyle(palette.ink)
                    Text("Open source under the MIT licence.")
                        .font(.subheadline)
                        .foregroundStyle(palette.mutedInk)

                    ActionCardView(
                        systemImage: "arrow.up.right.square",
                        title: "Source code",
                        subtitle: "GitHub repository",
                        action: {
                            if let url = URL(string: AppConfig.repoURL) { openURL(url) }
                        }
                    )
                    ActionCardView(
                        systemImage: "exclamationmark.bubble",
                        title: "Report a problem",
                        subtitle: "Open an issue on GitHub",
                        action: {
                            if let url = URL(string: AppConfig.issuesURL) { openURL(url) }
                        }
                    )
                    ActionCardView(
                        systemImage: "hand.raised",
                        title: "Privacy",
                        subtitle: "How the website handles data",
                        action: { openWeb("privacy/") }
                    )
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
                )
            }
            .padding(16)
        }
        .background(palette.background)
        .navigationTitle("Settings")
        .alert("Delete all app data?", isPresented: $confirmDelete) {
            Button("Delete", role: .destructive) {
                store.clearAll()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes completed topics, your streak, planner tasks and settings from this app. It cannot be undone.")
        }
    }
}
