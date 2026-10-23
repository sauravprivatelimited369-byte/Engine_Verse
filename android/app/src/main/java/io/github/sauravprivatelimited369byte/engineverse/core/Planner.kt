package io.github.sauravprivatelimited369byte.engineverse.core

data class PlannerTask(
    val id: String,
    val title: String,
    /** Epoch day the task is due, or null for "no date". */
    val dueDay: Long?,
    val done: Boolean,
    val createdAt: Long,
)

/** Pure planner operations; storage lives in AppStore. */
object PlannerRules {
    const val MAX_TITLE = 120
    const val MAX_TASKS = 200

    fun cleanTitle(raw: String): String? {
        val title = raw.replace(Regex("\\s+"), " ").trim()
        return if (title.isEmpty()) null else title.take(MAX_TITLE)
    }

    fun add(tasks: List<PlannerTask>, rawTitle: String, dueDay: Long?, id: String, now: Long): List<PlannerTask> {
        val title = cleanTitle(rawTitle) ?: return tasks
        if (tasks.size >= MAX_TASKS) return tasks
        return tasks + PlannerTask(id = id, title = title, dueDay = dueDay, done = false, createdAt = now)
    }

    fun toggle(tasks: List<PlannerTask>, id: String): List<PlannerTask> =
        tasks.map { if (it.id == id) it.copy(done = !it.done) else it }

    fun remove(tasks: List<PlannerTask>, id: String): List<PlannerTask> = tasks.filterNot { it.id == id }

    fun clearDone(tasks: List<PlannerTask>): List<PlannerTask> = tasks.filterNot { it.done }

    /** Open tasks first (soonest due, undated last), then finished ones, newest first. */
    fun sorted(tasks: List<PlannerTask>): List<PlannerTask> {
        val open = tasks.filter { !it.done }
            .sortedWith(compareBy<PlannerTask>({ it.dueDay ?: Long.MAX_VALUE }, { it.createdAt }))
        val done = tasks.filter { it.done }.sortedByDescending { it.createdAt }
        return open + done
    }

    fun nextUp(tasks: List<PlannerTask>): PlannerTask? = sorted(tasks).firstOrNull { !it.done }

    fun dueLabel(dueDay: Long?, today: Long): String? = when {
        dueDay == null -> null
        dueDay < today -> "Overdue"
        dueDay == today -> "Due today"
        dueDay == today + 1 -> "Due tomorrow"
        else -> "Due in ${dueDay - today} days"
    }
}
