import MeridianCore
import SwiftUI

struct LearnView: View {
    @ObservedObject var store: AppStore
    let catalog: Catalog
    let openWeb: (String) -> Void

    @State private var query = ""
    @State private var selectedGroup: String = ""
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        let filtered = CatalogSearch.filter(
            catalog.subjects,
            query: query,
            group: selectedGroup.isEmpty ? nil : selectedGroup
        )

        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        GroupChip(title: "All (\(catalog.subjects.count))", selected: selectedGroup.isEmpty) {
                            selectedGroup = ""
                        }
                        ForEach(catalog.groups, id: \.self) { group in
                            GroupChip(title: group, selected: selectedGroup == group) {
                                selectedGroup = selectedGroup == group ? "" : group
                            }
                        }
                    }
                    .padding(.vertical, 2)
                }

                if filtered.isEmpty {
                    Text("No subjects matched your search.")
                        .font(.subheadline)
                        .foregroundStyle(palette.mutedInk)
                        .padding(.vertical, 24)
                        .frame(maxWidth: .infinity)
                } else {
                    ForEach(filtered) { subject in
                        let doneCount = subject.topics.filter { store.isCompleted($0.slug) }.count
                        NavigationLink {
                            SubjectDetailView(store: store, subject: subject, openWeb: openWeb)
                        } label: {
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Text(subject.group.isEmpty ? "Engineering" : subject.group)
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(palette.primary)
                                    Spacer()
                                    Text("\(doneCount)/\(subject.topics.count) topics")
                                        .font(.caption)
                                        .foregroundStyle(palette.mutedInk)
                                }
                                Text(subject.name)
                                    .font(.headline)
                                    .foregroundStyle(palette.ink)
                                    .multilineTextAlignment(.leading)
                                if !subject.description.isEmpty {
                                    Text(subject.description)
                                        .font(.subheadline)
                                        .foregroundStyle(palette.mutedInk)
                                        .lineLimit(2)
                                        .multilineTextAlignment(.leading)
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
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(16)
        }
        .background(palette.background)
        .navigationTitle("Subjects")
        .searchable(text: $query, prompt: "Search subjects, topics or tags")
    }
}

private struct GroupChip: View {
    let title: String
    let selected: Bool
    let action: () -> Void
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        Button(action: action) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(selected ? Color.white : palette.ink)
                .padding(.horizontal, 12)
                .padding(.vertical, 7)
                .background(selected ? palette.primary : palette.surface, in: Capsule())
                .overlay(Capsule().strokeBorder(selected ? palette.primary : palette.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

struct SubjectDetailView: View {
    @ObservedObject var store: AppStore
    let subject: Subject
    let openWeb: (String) -> Void
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 10) {
                if !subject.description.isEmpty {
                    Text(subject.description)
                        .font(.subheadline)
                        .foregroundStyle(palette.mutedInk)
                        .padding(.bottom, 4)
                }
                ForEach(subject.topics) { topic in
                    let done = store.isCompleted(topic.slug)
                    NavigationLink {
                        TopicDetailView(store: store, subject: subject, topic: topic, openWeb: openWeb)
                    } label: {
                        HStack(alignment: .top, spacing: 12) {
                            Image(systemName: done ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(done ? palette.ok : palette.mutedInk)
                                .padding(.top, 2)
                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 6) {
                                    Text(topic.title)
                                        .font(.headline)
                                        .foregroundStyle(palette.ink)
                                        .multilineTextAlignment(.leading)
                                    if !topic.reviewed {
                                        Text("Draft")
                                            .font(.caption2.weight(.semibold))
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 2)
                                            .background(palette.surfaceVariant, in: Capsule())
                                            .foregroundStyle(palette.mutedInk)
                                    }
                                }
                                if !topic.summary.isEmpty {
                                    Text(topic.summary)
                                        .font(.subheadline)
                                        .foregroundStyle(palette.mutedInk)
                                        .lineLimit(2)
                                        .multilineTextAlignment(.leading)
                                }
                                HStack(spacing: 8) {
                                    if topic.minutes > 0 {
                                        Text("\(topic.minutes) min")
                                    }
                                    if !topic.difficulty.isEmpty {
                                        Text(topic.difficulty)
                                    }
                                }
                                .font(.caption)
                                .foregroundStyle(palette.mutedInk)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.caption)
                                .foregroundStyle(palette.mutedInk)
                        }
                        .padding(14)
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(16)
        }
        .background(palette.background)
        .navigationTitle(subject.name)
    }
}

struct TopicDetailView: View {
    @ObservedObject var store: AppStore
    let subject: Subject
    let topic: Topic
    let openWeb: (String) -> Void
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        let done = store.isCompleted(topic.slug)

        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(subject.name)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(palette.primary)

                Text(topic.title)
                    .font(.system(.title, design: .serif, weight: .semibold))
                    .foregroundStyle(palette.ink)

                HStack(spacing: 8) {
                    if topic.minutes > 0 {
                        Label("\(topic.minutes) min", systemImage: "clock")
                            .font(.caption)
                    }
                    if !topic.difficulty.isEmpty {
                        Text(topic.difficulty.capitalized)
                            .font(.caption.weight(.medium))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(palette.surfaceVariant, in: Capsule())
                    }
                    if !topic.reviewed {
                        Text("Draft — pending expert review")
                            .font(.caption)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(palette.surfaceVariant, in: Capsule())
                    }
                }
                .foregroundStyle(palette.mutedInk)

                if !topic.summary.isEmpty {
                    Text(topic.summary)
                        .font(.body)
                        .foregroundStyle(palette.ink)
                        .padding(16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
                        )
                }

                if !topic.tags.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(topic.tags, id: \.self) { tag in
                                Text("#\(tag)")
                                    .font(.caption)
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 5)
                                    .background(palette.surfaceVariant, in: Capsule())
                                    .foregroundStyle(palette.mutedInk)
                            }
                        }
                    }
                }

                HStack(spacing: 12) {
                    Button {
                        openWeb("topics/\(topic.slug)/")
                    } label: {
                        Label("Read full notes", systemImage: "book")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)

                    Button {
                        store.toggleTopic(topic.slug)
                    } label: {
                        Label(done ? "Completed" : "Mark complete", systemImage: done ? "checkmark.circle.fill" : "circle")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                }
            }
            .padding(16)
        }
        .background(palette.background)
        .navigationTitle(topic.title)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }
}
