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
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import io.github.sauravprivatelimited369byte.engineverse.core.Catalog
import io.github.sauravprivatelimited369byte.engineverse.data.AppStore

@Composable
fun PortfolioScreen(store: AppStore, catalog: Catalog, openTopic: (String) -> Unit) {
    val context = LocalContext.current
    val streak = store.streak
    val bySubject = remember(store.completedTopics, catalog) {
        store.completedTopics.mapNotNull { catalog.topic(it) }
            .groupBy({ it.first }, { it.second })
            .toList()
            .sortedBy { it.first.name }
    }
    val tasksDone = store.tasks.count { it.done }

    ScreenScaffold(title = "Learning record") { inner ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(inner),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Text(
                    "A record of what you marked complete on this phone. It is not verified by anyone and is not a " +
                        "certificate; share it as a summary of your own study.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    StatCard("${store.completedTopics.size}", "topics", Modifier.weight(1f))
                    StatCard("${bySubject.size}", "subjects", Modifier.weight(1f))
                    StatCard("${streak.longest}", "best streak", Modifier.weight(1f))
                }
            }
            item {
                Button(
                    onClick = {
                        val lines = buildString {
                            append("My Forge study record (self-reported)\n")
                            append("${store.completedTopics.size} topics across ${bySubject.size} subjects; ")
                            append("best streak ${streak.longest} days; $tasksDone planner tasks finished.\n")
                            bySubject.forEach { (subject, topics) ->
                                append("\n${subject.name}: ").append(topics.joinToString(", ") { it.title })
                            }
                        }
                        shareText(context, "My Forge study record", lines)
                    },
                    enabled = store.completedTopics.isNotEmpty(),
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Share summary") }
            }
            if (bySubject.isEmpty()) {
                item { EmptyText("Nothing yet. Open a subject, read a topic and mark it complete; it appears here.") }
            }
            items(bySubject, key = { it.first.slug }) { (subject, topics) ->
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        SectionTitle(subject.name)
                        Text(
                            "${topics.size} of ${subject.topics.size} topics",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        topics.forEach { topic ->
                            androidx.compose.material3.TextButton(onClick = { openTopic(topic.slug) }) { Text(topic.title) }
                        }
                    }
                }
            }
        }
    }
}
