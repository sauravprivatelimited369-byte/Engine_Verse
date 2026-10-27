import MeridianCore
import SwiftUI

/// Full notes, on the device. Every topic is bundled at four depths, so reading
/// needs no connection and opens no web page; the website stays available for
/// interactive diagrams, 3D models and the code playground.
struct NotesView: View {
    @ObservedObject var store: AppStore
    let catalog: Catalog
    let library: LessonLibrary
    let slug: String
    let openWeb: (String) -> Void

    @State private var level = ""
    @Environment(\.colorScheme) private var scheme

    private var available: [String] { library.availableLevels(slug) }
    private var activeLevel: String {
        available.contains(level) ? level : (available.first ?? "standard")
    }

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        let pair = catalog.topic(slug)
        let sections = library.sections(topic: slug, level: activeLevel)
        let questions = library.questions(forTopic: slug)
        let formulas = library.formulas[slug] ?? []
        let done = store.isCompleted(slug)

        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let pair {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(pair.0.name)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(palette.primary)
                        Text(pair.1.title)
                            .font(.system(.title2, design: .serif, weight: .semibold))
                            .foregroundStyle(palette.ink)
                        HStack(spacing: 8) {
                            if pair.1.minutes > 0 {
                                Label("\(pair.1.minutes) min", systemImage: "clock").font(.caption)
                            }
                            if !pair.1.difficulty.isEmpty {
                                Text(pair.1.difficulty.capitalized)
                                    .font(.caption.weight(.medium))
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(palette.surfaceVariant, in: Capsule())
                            }
                            if done {
                                Label("Completed", systemImage: "checkmark.circle.fill")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(palette.ok)
                            }
                        }
                        .foregroundStyle(palette.mutedInk)
                    }
                }

                if available.count > 1 {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(available, id: \.self) { option in
                                Button {
                                    level = option
                                } label: {
                                    Text(LessonLibrary.levelName(option))
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(option == activeLevel ? Color.white : palette.ink)
                                        .padding(.horizontal, 12)
                                        .padding(.vertical, 7)
                                        .background(
                                            option == activeLevel ? palette.primary : palette.surface,
                                            in: Capsule()
                                        )
                                        .overlay(
                                            Capsule().strokeBorder(
                                                option == activeLevel ? palette.primary : palette.border,
                                                lineWidth: 1
                                            )
                                        )
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                }

                if library.isEmpty {
                    Text("The offline lesson library is still loading. It is bundled with the app, so no connection is needed.")
                        .font(.subheadline)
                        .foregroundStyle(palette.mutedInk)
                } else if sections.isEmpty {
                    Text("This topic's notes are not in the bundled library yet. You can still open the full note on the website.")
                        .font(.subheadline)
                        .foregroundStyle(palette.mutedInk)
                } else {
                    ForEach(Array(sections.enumerated()), id: \.offset) { _, section in
                        SectionCardView(section: section, palette: palette)
                    }
                }

                if !formulas.isEmpty {
                    Text("Formulas")
                        .font(.headline)
                        .foregroundStyle(palette.ink)
                        .padding(.top, 4)
                    ForEach(Array(formulas.enumerated()), id: \.offset) { _, formula in
                        FormulaCardView(formula: formula, palette: palette)
                    }
                }

                VStack(spacing: 10) {
                    if !questions.isEmpty {
                        NavigationLink {
                            PracticeView(
                                store: store,
                                catalog: catalog,
                                library: library,
                                topicFilter: slug,
                                openWeb: openWeb
                            )
                        } label: {
                            Label(
                                "Practise \(questions.count) question\(questions.count == 1 ? "" : "s") on this topic",
                                systemImage: "checklist"
                            )
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                    }

                    Button {
                        store.toggleTopic(slug)
                    } label: {
                        Label(done ? "Mark as not done" : "Mark complete",
                              systemImage: done ? "checkmark.circle.fill" : "circle")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)

                    Button {
                        openWeb("topics/\(slug)/")
                    } label: {
                        Label("Open diagrams and extras on the website", systemImage: "safari")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)

                    Text("Notes and practice questions are built into the app and work offline. The website is only used for interactive diagrams, 3D models and the code playground.")
                        .font(.caption)
                        .foregroundStyle(palette.mutedInk)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(.top, 6)
            }
            .padding(16)
        }
        .background(palette.background)
        .navigationTitle(pair?.1.title ?? "Notes")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }
}

private struct SectionCardView: View {
    let section: LessonSection
    let palette: MeridianPalette

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(section.title)
                    .font(.headline)
                    .foregroundStyle(palette.ink)
                if !section.callout.isEmpty {
                    let colors = CalloutStyle.colors(section.callout, palette: palette)
                    Text(section.callout.capitalized)
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(colors.0, in: Capsule())
                        .foregroundStyle(colors.1)
                }
            }
            BlocksView(blocks: section.blocks)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
        )
    }
}

private struct FormulaCardView: View {
    let formula: Formula
    let palette: MeridianPalette

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(formula.name)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(palette.ink)
            ScrollView(.horizontal, showsIndicators: false) {
                Text(verbatim: formula.plain)
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(palette.ink)
                    .padding(10)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(palette.surfaceVariant, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            if !formula.meaning.isEmpty {
                Text(formula.meaning)
                    .font(.caption)
                    .foregroundStyle(palette.mutedInk)
            }
            if !formula.application.isEmpty {
                Text("Where it is used: \(formula.application)")
                    .font(.caption)
                    .foregroundStyle(palette.mutedInk)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
        )
    }
}
