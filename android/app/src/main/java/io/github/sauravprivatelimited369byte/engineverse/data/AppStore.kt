package io.github.sauravprivatelimited369byte.engineverse.data

import android.content.Context
import android.content.SharedPreferences
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.edit
import io.github.sauravprivatelimited369byte.engineverse.core.PlannerRules
import io.github.sauravprivatelimited369byte.engineverse.core.PlannerTask
import io.github.sauravprivatelimited369byte.engineverse.core.Streak
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.util.UUID

enum class ThemeMode { SYSTEM, LIGHT, DARK }

/**
 * Everything the app remembers, in one private SharedPreferences file
 * ("engineverse.xml"). There is no account and nothing is uploaded: progress,
 * the streak, planner tasks and the theme choice stay on this device (and in
 * the user's own Android backup, see res/xml/data_extraction_rules.xml).
 */
class AppStore private constructor(context: Context) {
    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    /** Completed topic slugs, oldest first. */
    var completedTopics by mutableStateOf(readStringList(KEY_COMPLETED))
        private set

    var activityDays by mutableStateOf(readDays())
        private set

    var tasks by mutableStateOf(readTasks())
        private set

    var themeMode by mutableStateOf(readTheme())
        private set

    val streak: Streak.Result get() = Streak.compute(activityDays, Streak.today())

    fun isCompleted(slug: String): Boolean = slug in completedTopics

    fun toggleTopic(slug: String) {
        completedTopics = if (slug in completedTopics) {
            completedTopics - slug
        } else {
            recordActivity()
            completedTopics + slug
        }
        prefs.edit { putString(KEY_COMPLETED, JSONArray(completedTopics).toString()) }
    }

    fun recordActivity() {
        val today = Streak.today()
        if (today in activityDays) return
        // Keep about two years of history; older days cannot change a streak's display.
        activityDays = (activityDays + today).filter { it > today - 730 }.toSet()
        prefs.edit { putStringSet(KEY_DAYS, activityDays.map { it.toString() }.toSet()) }
    }

    fun addTask(title: String, dueDay: Long?) {
        updateTasks(PlannerRules.add(tasks, title, dueDay, UUID.randomUUID().toString(), System.currentTimeMillis()))
    }

    fun toggleTask(id: String) {
        val before = tasks.firstOrNull { it.id == id }
        updateTasks(PlannerRules.toggle(tasks, id))
        if (before != null && !before.done) recordActivity()
    }

    fun removeTask(id: String) = updateTasks(PlannerRules.remove(tasks, id))

    fun clearDoneTasks() = updateTasks(PlannerRules.clearDone(tasks))

    fun setTheme(mode: ThemeMode) {
        themeMode = mode
        prefs.edit { putString(KEY_THEME, mode.name) }
    }

    /** Deletes everything this app stored (the website's own data is separate). */
    fun clearAll() {
        prefs.edit { clear() }
        completedTopics = emptyList()
        activityDays = emptySet()
        tasks = emptyList()
        themeMode = ThemeMode.SYSTEM
    }

    private fun updateTasks(next: List<PlannerTask>) {
        tasks = next
        val array = JSONArray()
        next.forEach { task ->
            array.put(
                JSONObject()
                    .put("id", task.id)
                    .put("title", task.title)
                    .put("due", task.dueDay ?: JSONObject.NULL)
                    .put("done", task.done)
                    .put("created", task.createdAt),
            )
        }
        prefs.edit { putString(KEY_TASKS, array.toString()) }
    }

    private fun readStringList(key: String): List<String> = try {
        val array = JSONArray(prefs.getString(key, "[]") ?: "[]")
        (0 until array.length()).mapNotNull { i -> array.optString(i).takeIf { SLUG.matches(it) } }.distinct()
    } catch (e: JSONException) {
        emptyList()
    }

    private fun readDays(): Set<Long> =
        prefs.getStringSet(KEY_DAYS, emptySet()).orEmpty().mapNotNull { it.toLongOrNull() }.toSet()

    private fun readTasks(): List<PlannerTask> = try {
        val array = JSONArray(prefs.getString(KEY_TASKS, "[]") ?: "[]")
        (0 until array.length()).mapNotNull { i ->
            val o = array.optJSONObject(i) ?: return@mapNotNull null
            val title = PlannerRules.cleanTitle(o.optString("title")) ?: return@mapNotNull null
            PlannerTask(
                id = o.optString("id").ifBlank { UUID.randomUUID().toString() },
                title = title,
                dueDay = if (o.isNull("due")) null else o.optLong("due"),
                done = o.optBoolean("done"),
                createdAt = o.optLong("created"),
            )
        }.take(PlannerRules.MAX_TASKS)
    } catch (e: JSONException) {
        emptyList()
    }

    private fun readTheme(): ThemeMode =
        ThemeMode.entries.firstOrNull { it.name == prefs.getString(KEY_THEME, null) } ?: ThemeMode.SYSTEM

    companion object {
        private const val FILE = "engineverse"
        private const val KEY_COMPLETED = "completed_topics"
        private const val KEY_DAYS = "activity_days"
        private const val KEY_TASKS = "planner_tasks"
        private const val KEY_THEME = "theme"
        private val SLUG = Regex("^[a-z0-9][a-z0-9-]{0,120}$")

        @Volatile
        private var instance: AppStore? = null

        fun get(context: Context): AppStore =
            instance ?: synchronized(this) { instance ?: AppStore(context).also { instance = it } }
    }
}
