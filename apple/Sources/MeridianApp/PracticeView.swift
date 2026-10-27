import MeridianCore
import SwiftUI

/// The practice bank is bundled with the app: 500+ multiple-choice questions
/// across the same subjects, answerable with no connection. Explanations are on
/// the device, and what you have answered is kept locally.
struct PracticeView: View {
    @ObservedObject var store: AppStore
    let catalog: Catalog
    let library: LessonLibrary
    let topicFilter: String?
    let openWeb: (String) -> Void

    @State private var query = ""
    @Environment(\.colorScheme) private var scheme

    private var all: [PracticeQuestion] {
        guard let topicFilter, !topicFilter.isEmpty else { return library.questions }
        return library.questions(forTopic: topicFilter)
    }

    private var visible: [PracticeQuestion] {
        let needle = query.trimmingCharacters(in: .whitespaces).lowercased()
        guard !needle.isEmpty else { return all }
        return all.filter { question in
            question.headline.lowercased().contains(needle)
                || question.topic.contains(needle)
                || question.subject.contains(needle)
                || (catalog.topic(question.topic)?.1.title.lowercased().contains(needle) ?? false)
        }
    }

    private var topicName: String? {
        guard let topicFilter, !topicFilter.isEmpty else { return nil }
        return catalog.topic(topicFilter)?.1.title
    }

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        let counts = Dictionary(grouping: library.questions, by: \.topic).mapValues(\.count)

        ScrollView {
            LazyVStack(alignment: .leading, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(store.answeredCount) answered · \(store.correctCount) correct")
                        .font(.headline)
                        .foregroundStyle(palette.onPrimaryContainer)
                    Text("\(library.questions.count) questions are built into the app and work offline.")
                        .font(.caption)
                        .foregroundStyle(palette.onPrimaryContainer.opacity(0.85))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(16)
                .background(palette.primaryContainer, in: RoundedRectangle(cornerRadius: 14, style: .continuous))

                if let topicName {
                    Text("Showing questions for \(topicName) only.")
                        .font(.caption)
                        .foregroundStyle(palette.mutedInk)
                }

                if library.isEmpty {
                    Text("The offline question bank is still loading. It is bundled with the app.")
                        .font(.subheadline)
                        .foregroundStyle(palette.mutedInk)
                } else if visible.isEmpty {
                    Text("No question matches \u{201C}\(query)\u{201D}.")
                        .font(.subheadline)
                        .foregroundStyle(palette.mutedInk)
                }

                ForEach(visible) { question in
                    NavigationLink {
                        QuestionView(
                            store: store,
                            catalog: catalog,
                            library: library,
                            slug: question.slug,
                            openWeb: openWeb
                        )
                    } label: {
                        QuestionCard(
                            question: question,
                            topicTitle: catalog.topic(question.topic)?.1.title,
                            topicQuestionCount: counts[question.topic] ?? 0,
                            answered: store.isAnswered(question.slug),
                            correct: store.wasCorrect(question.slug),
                            palette: palette
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(16)
        }
        .background(palette.background)
        .navigationTitle(topicName.map { "Practice · \($0)" } ?? "Practice")
        .searchable(text: $query, prompt: "Search questions")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }
}

private struct QuestionCard: View {
    let question: PracticeQuestion
    let topicTitle: String?
    let topicQuestionCount: Int
    let answered: Bool
    let correct: Bool
    let palette: MeridianPalette

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(question.headline)
                .font(.body)
                .foregroundStyle(palette.ink)
                .multilineTextAlignment(.leading)
            HStack(spacing: 6) {
                QuestionTag(text: question.difficulty, palette: palette)
                if let topicTitle {
                    QuestionTag(text: topicTitle, palette: palette)
                }
                if correct {
                    QuestionTag(text: "Correct", palette: palette, tint: palette.ok)
                } else if answered {
                    QuestionTag(text: "Missed", palette: palette, tint: palette.primary)
                } else {
                    QuestionTag(text: "New", palette: palette)
                }
            }
            if topicQuestionCount > 1 {
                Text("\(topicQuestionCount) questions on this topic")
                    .font(.caption2)
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

struct QuestionTag: View {
    let text: String
    let palette: MeridianPalette
    var tint: Color?

    var body: some View {
        Text(text)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(palette.surfaceVariant, in: Capsule())
            .foregroundStyle(tint ?? palette.mutedInk)
    }
}

struct QuestionView: View {
    @ObservedObject var store: AppStore
    let catalog: Catalog
    let library: LessonLibrary
    let slug: String
    let openWeb: (String) -> Void

    @State private var chosen = ""
    @State private var checked = false
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        let question = library.question(slug)

        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let question {
                    let correctOption = question.options.first { $0.correct }
                    let isRight = question.options.first { $0.label == chosen }?.correct == true
                    let next = nextQuestion(after: question)

                    HStack(spacing: 6) {
                        QuestionTag(text: question.difficulty, palette: palette)
                        if let title = catalog.topic(question.topic)?.1.title {
                            QuestionTag(text: title, palette: palette)
                        }
                    }

                    BlocksView(blocks: question.stem)

                    if !question.context.isEmpty {
                        BlocksView(blocks: question.context)
                            .padding(12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(palette.surfaceVariant, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    }

                    ForEach(question.options, id: \.label) { option in
                        OptionRow(
                            option: option,
                            selected: chosen == option.label,
                            checked: checked,
                            palette: palette
                        ) {
                            if !checked { chosen = option.label }
                        }
                    }

                    if !checked {
                        Button {
                            guard !chosen.isEmpty else { return }
                            checked = true
                            store.answer(question.slug, correct: isRight)
                        } label: {
                            Text("Check answer").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                        .disabled(chosen.isEmpty)
                    } else {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(isRight ? "Correct" : "Not quite — the answer is \(correctOption?.label ?? "not shown")")
                                .font(.headline)
                                .foregroundStyle(isRight ? palette.ok : palette.ink)
                            BlocksView(blocks: question.explanation)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(14)
                        .background(
                            isRight ? palette.primaryContainer : palette.surfaceVariant,
                            in: RoundedRectangle(cornerRadius: 14, style: .continuous)
                        )

                        Button {
                            chosen = ""
                            checked = false
                        } label: {
                            Text("Try this question again").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.large)

                        if let next {
                            NavigationLink {
                                QuestionView(
                                    store: store,
                                    catalog: catalog,
                                    library: library,
                                    slug: next.slug,
                                    openWeb: openWeb
                                )
                            } label: {
                                Text("Next question").frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.large)
                        }

                        NavigationLink {
                            NotesView(
                                store: store,
                                catalog: catalog,
                                library: library,
                                slug: question.topic,
                                openWeb: openWeb
                            )
                        } label: {
                            Text("Read the notes for this topic").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.large)
                    }
                } else {
                    Text("This question is not in the bundled bank.")
                        .font(.subheadline)
                        .foregroundStyle(palette.mutedInk)
                }
            }
            .padding(16)
        }
        .background(palette.background)
        .navigationTitle(topicTitle)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }

    private var topicTitle: String {
        guard let question = library.question(slug) else { return "Question" }
        return catalog.topic(question.topic)?.1.title ?? "Question"
    }

    private func nextQuestion(after question: PracticeQuestion) -> PracticeQuestion? {
        guard let index = library.questions.firstIndex(where: { $0.slug == question.slug }),
              index + 1 < library.questions.count
        else { return nil }
        return library.questions[index + 1]
    }
}

private struct OptionRow: View {
    let option: PracticeOption
    let selected: Bool
    let checked: Bool
    let palette: MeridianPalette
    let action: () -> Void

    var body: some View {
        let container: Color = {
            if checked && option.correct { return palette.primaryContainer }
            if checked && selected { return palette.surfaceVariant }
            if selected { return palette.primaryContainer }
            return palette.surface
        }()

        Button(action: action) {
            HStack(alignment: .top, spacing: 10) {
                Text("\(option.label).")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(palette.ink)
                BlocksView(blocks: option.body)
                if checked && (option.correct || selected) {
                    Image(systemName: option.correct ? "checkmark.circle.fill" : "xmark.circle")
                        .foregroundStyle(option.correct ? palette.ok : palette.mutedInk)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(container, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}
