import MeridianCore
import SwiftUI

struct PortfolioView: View {
    @ObservedObject var store: AppStore
    let catalog: Catalog
    let openWeb: (String) -> Void
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        let streak = store.streak
        let grouped = groupedTopics()

        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("A record of what you marked complete on this device. It is not verified by anyone and is not a certificate; share it as a summary of your own study.")
                    .font(.subheadline)
                    .foregroundStyle(palette.mutedInk)

                HStack(spacing: 10) {
                    StatCardView(value: "\(store.completedTopics.count)", label: "topics")
                    StatCardView(value: "\(grouped.count)", label: "subjects")
                    StatCardView(value: "\(streak.longest)", label: "best streak")
                }

                if !store.completedTopics.isEmpty {
                    ShareLink(
                        item: store.summaryText(catalog: catalog),
                        subject: Text("My Meridian study record")
                    ) {
                        Label("Share summary", systemImage: "square.and.arrow.up")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                }

                if grouped.isEmpty {
                    Text("Nothing yet. Open a subject, read a topic and mark it complete; it appears here.")
                        .font(.subheadline)
                        .foregroundStyle(palette.mutedInk)
                        .padding(.vertical, 20)
                } else {
                    ForEach(grouped, id: \.0.slug) { subject, topics in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text(subject.name)
                                    .font(.headline)
                                    .foregroundStyle(palette.ink)
                                Spacer()
                                Text("\(topics.count) of \(subject.topics.count) topics")
                                    .font(.caption)
                                    .foregroundStyle(palette.mutedInk)
                            }
                            ForEach(topics) { topic in
                                NavigationLink {
                                    TopicDetailView(store: store, subject: subject, topic: topic, openWeb: openWeb)
                                } label: {
                                    HStack {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundStyle(palette.ok)
                                            .font(.subheadline)
                                        Text(topic.title)
                                            .font(.subheadline)
                                            .foregroundStyle(palette.primary)
                                        Spacer()
                                    }
                                    .padding(.vertical, 2)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
                        )
                    }
                }
            }
            .padding(16)
        }
        .background(palette.background)
        .navigationTitle("Learning record")
    }

    private func groupedTopics() -> [(Subject, [Topic])] {
        let pairs = store.completedTopics.compactMap { catalog.topic($0) }
        let dict = Dictionary(grouping: pairs, by: { $0.0.slug })
        return dict.values
            .compactMap { list -> (Subject, [Topic])? in
                guard let subject = list.first?.0 else { return nil }
                return (subject, list.map(\.1))
            }
            .sorted { $0.0.name.localizedCaseInsensitiveCompare($1.0.name) == .orderedAscending }
    }
}
