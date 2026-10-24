import MeridianCore
import SwiftUI

struct PlannerView: View {
    @ObservedObject var store: AppStore
    @State private var draftTitle = ""
    @State private var hasDueDate = false
    @State private var dueDate = Date()
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        let sortedTasks = PlannerRules.sorted(store.tasks)
        let today = Streak.today()

        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 10) {
                    Text("New study task")
                        .font(.headline)
                        .foregroundStyle(palette.ink)

                    TextField("e.g. Revise Kirchhoff's laws or solve Two Sum", text: $draftTitle)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit(submitTask)

                    Toggle("Set due date", isOn: $hasDueDate)
                        .font(.subheadline)
                        .foregroundStyle(palette.ink)

                    if hasDueDate {
                        DatePicker("Due date", selection: $dueDate, displayedComponents: .date)
                            .font(.subheadline)
                    }

                    HStack {
                        Button("Add task", action: submitTask)
                            .buttonStyle(.borderedProminent)
                            .disabled(PlannerRules.cleanTitle(draftTitle) == nil)
                        Spacer()
                        if store.tasks.contains(where: \.done) {
                            Button("Clear completed") {
                                store.clearDoneTasks()
                            }
                            .font(.subheadline)
                        }
                    }
                }
                .padding(16)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
                )

                if sortedTasks.isEmpty {
                    Text("No tasks yet. Everything added here stays on this device.")
                        .font(.subheadline)
                        .foregroundStyle(palette.mutedInk)
                        .padding(.vertical, 20)
                        .frame(maxWidth: .infinity)
                } else {
                    ForEach(sortedTasks) { task in
                        HStack(spacing: 12) {
                            Button {
                                store.toggleTask(task.id)
                            } label: {
                                Image(systemName: task.done ? "checkmark.circle.fill" : "circle")
                                    .font(.title3)
                                    .foregroundStyle(task.done ? palette.ok : palette.mutedInk)
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel(task.done ? "Mark incomplete" : "Mark complete")

                            VStack(alignment: .leading, spacing: 3) {
                                Text(task.title)
                                    .font(.body)
                                    .strikethrough(task.done)
                                    .foregroundStyle(task.done ? palette.mutedInk : palette.ink)
                                if let dueLabel = PlannerRules.dueLabel(dueDay: task.dueDay, today: today) {
                                    Text(dueLabel)
                                        .font(.caption.weight(.medium))
                                        .foregroundStyle(!task.done && (task.dueDay ?? today) < today ? Color.red : palette.primary)
                                }
                            }
                            Spacer()
                            Button(role: .destructive) {
                                store.removeTask(task.id)
                            } label: {
                                Image(systemName: "trash")
                                    .font(.subheadline)
                                    .foregroundStyle(palette.mutedInk)
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel("Delete task")
                        }
                        .padding(14)
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
        .navigationTitle("Study planner")
    }

    private func submitTask() {
        guard PlannerRules.cleanTitle(draftTitle) != nil else { return }
        let dueDay = hasDueDate ? Streak.epochDay(for: dueDate) : nil
        store.addTask(title: draftTitle, dueDay: dueDay)
        draftTitle = ""
        hasDueDate = false
    }
}
