@file:OptIn(ExperimentalMaterial3Api::class)

package io.github.sauravprivatelimited369byte.engineverse.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import io.github.sauravprivatelimited369byte.engineverse.R
import io.github.sauravprivatelimited369byte.engineverse.core.Catalog
import io.github.sauravprivatelimited369byte.engineverse.core.PlannerRules
import io.github.sauravprivatelimited369byte.engineverse.core.Streak
import io.github.sauravprivatelimited369byte.engineverse.data.AppStore

@Composable
fun HomeScreen(store: AppStore, catalog: Catalog, navigate: (String) -> Unit, openWeb: (String) -> Unit) {
    val streak = store.streak
    val next = PlannerRules.nextUp(store.tasks)
    val recent = store.completedTopics.takeLast(3).reversed().mapNotNull { catalog.topic(it) }

    ScreenScaffold(
        title = "FORGE",
        actions = {
            IconButton(onClick = { navigate(Routes.SETTINGS) }) {
                Icon(painterResource(R.drawable.ic_tune), contentDescription = "Settings")
            }
        },
    ) { inner ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(inner),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.primaryContainer,
                        contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
                    ),
                ) {
                    Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(
                            "Where engineers are made.",
                            style = MaterialTheme.typography.headlineSmall,
                            modifier = Modifier.semantics { heading() },
                        )
                        Text(
                            "${catalog.subjects.size} subjects and ${catalog.topicCount} topics are on this phone and " +
                                "work offline. Full notes, practice questions and the code playground open from the website.",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                }
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    StatCard("${streak.current}", "day streak", Modifier.weight(1f))
                    StatCard("${store.completedTopics.size}", "topics done", Modifier.weight(1f))
                    StatCard("${store.tasks.count { !it.done }}", "open tasks", Modifier.weight(1f))
                }
            }
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(Modifier.fillMaxWidth().padding(16.dp)) {
                        SectionTitle("Next up")
                        if (next == null) {
                            Text(
                                "No open tasks. Plan a topic, a problem set or a revision session.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        } else {
                            Text(next.title, style = MaterialTheme.typography.bodyLarge)
                            PlannerRules.dueLabel(next.dueDay, Streak.today())?.let {
                                Text(it, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                            }
                        }
                        TextButton(onClick = { navigate(Routes.PLANNER) }) { Text("Open planner") }
                    }
                }
            }
            item { SectionTitle("Start here", Modifier.padding(top = 4.dp)) }
            item {
                ActionCard(R.drawable.ic_book, "Browse subjects", "Search the offline catalogue and track topics", { navigate(Routes.LEARN) })
            }
            item {
                ActionCard(R.drawable.ic_code, "Code playground", "Write and run code in the browser runtimes", { navigate(Routes.PLAYGROUND) })
            }
            item {
                ActionCard(R.drawable.ic_calendar, "Daily practice", "Today's questions on the website", { openWeb("dpp/") })
            }
            item {
                ActionCard(R.drawable.ic_person, "Opportunities", "Internships, scholarships and contests with official links", { openWeb("opportunities/") })
            }
            if (recent.isNotEmpty()) {
                item { SectionTitle("Recently completed", Modifier.padding(top = 4.dp)) }
                items(recent, key = { it.second.slug }) { (subject, topic) ->
                    ActionCard(R.drawable.ic_check, topic.title, subject.name, { navigate(Routes.topic(topic.slug)) })
                }
            }
        }
    }
}
