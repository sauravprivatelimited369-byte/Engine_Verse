import MeridianCore
import SwiftUI

private struct RecentTopicItem: Identifiable {
    let subject: Subject
    let topic: Topic
    var id: String { topic.slug }
}

struct HomeView: View {
    @ObservedObject var store: AppStore
    let catalog: Catalog
    let selectSection: (AppSection) -> Void
    let openWeb: (String) -> Void

    @State private var showSettingsSheet = false
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        let streak = store.streak
        let nextTask = PlannerRules.nextUp(store.tasks)
        let recent: [RecentTopicItem] = store.completedTopics.suffix(3).reversed().compactMap { slug in
            guard let pair = catalog.topic(slug) else { return nil }
            return RecentTopicItem(subject: pair.0, topic: pair.1)
        }

        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Engineering, studied properly.")
                        .font(.system(.title2, design: .serif, weight: .semibold))
                        .foregroundStyle(palette.onPrimaryContainer)
                    Text("\(catalog.subjects.count) subjects and \(catalog.topicCount) topics are bundled on this device and work offline. Full notes, practice questions and the code playground open from the website.")
                        .font(.subheadline)
                        .foregroundStyle(palette.onPrimaryContainer.opacity(0.9))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(20)
                .background(palette.primaryContainer, in: RoundedRectangle(cornerRadius: 16, style: .continuous))

                HStack(spacing: 10) {
                    StatCardView(value: "\(streak.current)", label: "day streak")
                    StatCardView(value: "\(store.completedTopics.count)", label: "topics done")
                    StatCardView(value: "\(store.tasks.filter { !$0.done }.count)", label: "open tasks")
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Next up")
                        .font(.headline)
                        .foregroundStyle(palette.ink)
                    if let nextTask {
                        Text(nextTask.title)
                            .font(.body.weight(.medium))
                            .foregroundStyle(palette.ink)
                        if let label = PlannerRules.dueLabel(dueDay: nextTask.dueDay, today: Streak.today()) {
                            Text(label)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(palette.primary)
                        }
                    } else {
                        Text("No open tasks. Plan a topic, a problem set or a revision session.")
                            .font(.subheadline)
                            .foregroundStyle(palette.mutedInk)
                    }
                    Button("Open planner") {
                        selectSection(.planner)
                    }
                    .font(.subheadline.weight(.semibold))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(16)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
                )

                Text("Start here")
                    .font(.headline)
                    .foregroundStyle(palette.ink)
                    .padding(.top, 4)

                ActionCardView(
                    systemImage: "book.closed",
                    title: "Browse subjects",
                    subtitle: "Search the offline catalogue and track topics",
                    action: { selectSection(.learn) }
                )
                ActionCardView(
                    systemImage: "chevron.left.forwardslash.chevron.right",
                    title: "Code playground",
                    subtitle: "Write and run code in the browser runtimes",
                    action: { selectSection(.playground) }
                )
                ActionCardView(
                    systemImage: "calendar.badge.checkmark",
                    title: "Daily practice",
                    subtitle: "Today's questions on the website",
                    action: { openWeb("dpp/") }
                )
                ActionCardView(
                    systemImage: "sparkles.rectangle.stack",
                    title: "Opportunities",
                    subtitle: "Internships, scholarships and contests with official links",
                    action: { openWeb("opportunities/") }
                )

                if !recent.isEmpty {
                    Text("Recently completed")
                        .font(.headline)
                        .foregroundStyle(palette.ink)
                        .padding(.top, 4)
                    ForEach(recent) { item in
                        NavigationLink {
                            TopicDetailView(store: store, subject: item.subject, topic: item.topic, openWeb: openWeb)
                        } label: {
                            HStack {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(palette.ok)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(item.topic.title)
                                        .font(.headline)
                                        .foregroundStyle(palette.ink)
                                    Text(item.subject.name)
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
            }
            .padding(16)
        }
        .background(palette.background)
        .navigationTitle("Meridian")
        #if os(iOS)
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button {
                    showSettingsSheet = true
                } label: {
                    Image(systemName: "gearshape")
                        .accessibilityLabel("Settings")
                }
            }
        }
        .sheet(isPresented: $showSettingsSheet) {
            NavigationStack {
                SettingsView(store: store, openWeb: { path in
                    showSettingsSheet = false
                    openWeb(path)
                })
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Done") { showSettingsSheet = false }
                    }
                }
            }
        }
        #endif
    }
}
