import MeridianCore
import SwiftUI

struct PlaygroundView: View {
    let openWeb: (String) -> Void
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Code runs on the website's in-browser runtimes (WebAssembly in a separate worker), shown here inside the app. Each language downloads its runtime the first time you run it, so you need a connection; a runaway program is stopped by the time limit. Nothing is sent to a server to execute. Each page lists which languages it can run before you start.")
                    .font(.subheadline)
                    .foregroundStyle(palette.ink)
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(palette.surfaceVariant, in: RoundedRectangle(cornerRadius: 14, style: .continuous))

                ActionCardView(
                    systemImage: "chevron.left.forwardslash.chevron.right",
                    title: "CodeLab",
                    subtitle: "Editor with a separate mode for each language",
                    action: { openWeb("codelab/") }
                )
                ActionCardView(
                    systemImage: "terminal",
                    title: "Code compiler",
                    subtitle: "Run a single file with input",
                    action: { openWeb("compiler/") }
                )
                ActionCardView(
                    systemImage: "play.rectangle",
                    title: "Python compiler",
                    subtitle: "CPython in the browser (Pyodide)",
                    action: { openWeb("python-compiler/") }
                )
                ActionCardView(
                    systemImage: "checklist",
                    title: "Coding problems",
                    subtitle: "Judged problems with test cases",
                    action: { openWeb("practice/problems/") }
                )
            }
            .padding(16)
        }
        .background(palette.background)
        .navigationTitle("Code playground")
    }
}
