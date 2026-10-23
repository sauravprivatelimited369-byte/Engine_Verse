@file:OptIn(ExperimentalMaterial3Api::class)

package io.github.sauravprivatelimited369byte.engineverse.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import io.github.sauravprivatelimited369byte.engineverse.R
import io.github.sauravprivatelimited369byte.engineverse.core.PlannerRules
import io.github.sauravprivatelimited369byte.engineverse.core.Streak
import io.github.sauravprivatelimited369byte.engineverse.data.AppStore

private enum class Due(val label: String, val offset: Long?) {
    NONE("No date", null), TODAY("Today", 0), TOMORROW("Tomorrow", 1), WEEK("In a week", 7)
}

@Composable
fun PlannerScreen(store: AppStore) {
    var draft by rememberSaveable { mutableStateOf("") }
    var due by rememberSaveable { mutableStateOf(Due.NONE) }
    val today = Streak.today()
    val tasks = remember(store.tasks) { PlannerRules.sorted(store.tasks) }
    val full = store.tasks.size >= PlannerRules.MAX_TASKS

    fun submit() {
        if (PlannerRules.cleanTitle(draft) == null || full) return
        store.addTask(draft, due.offset?.let { today + it })
        draft = ""
        due = Due.NONE
    }

    ScreenScaffold(title = "Study planner") { inner ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(inner),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedTextField(
                                value = draft,
                                onValueChange = { draft = it.take(PlannerRules.MAX_TITLE) },
                                modifier = Modifier.weight(1f),
                                singleLine = true,
                                label = { Text("What will you study?") },
                                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                                keyboardActions = KeyboardActions(onDone = { submit() }),
                            )
                            FilledIconButton(onClick = { submit() }, enabled = draft.isNotBlank() && !full) {
                                Icon(painterResource(R.drawable.ic_add), contentDescription = "Add task")
                            }
                        }
                        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Due.entries.forEach { option ->
                                FilterChip(selected = due == option, onClick = { due = option }, label = { Text(option.label) })
                            }
                        }
                        if (full) {
                            Text(
                                "The planner holds ${PlannerRules.MAX_TASKS} tasks. Clear finished ones to add more.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.error,
                            )
                        }
                    }
                }
            }
            if (tasks.isEmpty()) {
                item {
                    EmptyText("No tasks yet. Add a topic to read, a problem set, or a revision session. Tasks stay on this phone.")
                }
            }
            items(tasks, key = { it.id }) { task ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = task.done, onCheckedChange = { store.toggleTask(task.id) })
                    Column(Modifier.weight(1f)) {
                        Text(
                            task.title,
                            style = MaterialTheme.typography.bodyLarge,
                            textDecoration = if (task.done) TextDecoration.LineThrough else null,
                            color = if (task.done) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface,
                        )
                        PlannerRules.dueLabel(task.dueDay, today)?.takeIf { !task.done }?.let { label ->
                            Text(
                                label,
                                style = MaterialTheme.typography.labelMedium,
                                color = if (label == "Overdue") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                    IconButton(onClick = { store.removeTask(task.id) }) {
                        Icon(painterResource(R.drawable.ic_delete), contentDescription = "Delete ${task.title}")
                    }
                }
            }
            if (tasks.any { it.done }) {
                item {
                    TextButton(onClick = { store.clearDoneTasks() }) { Text("Clear finished tasks") }
                }
            }
        }
    }
}
