@file:OptIn(ExperimentalMaterial3Api::class)

package io.github.sauravprivatelimited369byte.engineverse.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.github.sauravprivatelimited369byte.engineverse.core.Catalog
import io.github.sauravprivatelimited369byte.engineverse.core.LessonLibrary
import io.github.sauravprivatelimited369byte.engineverse.core.LessonSection
import io.github.sauravprivatelimited369byte.engineverse.data.AppStore

/**
 * Full notes, on the device. Every topic is bundled at four depths, so reading
 * needs no connection and opens no web page; the website stays available for
 * diagrams and the code playground.
 */
@Composable
fun NotesScreen(
    store: AppStore,
    catalog: Catalog,
    library: LessonLibrary,
    slug: String,
    initialLevel: String,
    onBack: () -> Unit,
    onPractise: (String) -> Unit,
    openWeb: (String) -> Unit,
) {
    val entry = catalog.topic(slug)
    val title = entry?.second?.title ?: "Notes"
    val available = library.availableLevels(slug)
    var level by rememberSaveable(slug) {
        mutableStateOf(
            initialLevel.takeIf { it in available }
                ?: available.firstOrNull()
                ?: "standard",
        )
    }
    val sections = library.sections(slug, level)
    val questions = library.questionsForTopic(slug)

    ScreenScaffold(title = title, onBack = onBack) { inner ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(inner),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    entry?.let { (subject, topic) ->
                        Text(subject.name, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                        Text(topic.title, style = MaterialTheme.typography.headlineSmall)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Tag(topic.difficulty)
                            Tag("${topic.minutes} min")
                            if (store.isCompleted(topic.slug)) Tag("Completed")
                        }
                    }
                }
            }
            if (available.size > 1) {
                item {
                    Row(
                        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        available.forEach { option ->
                            FilterChip(
                                selected = option == level,
                                onClick = { level = option },
                                label = { Text(LessonLibrary.levelName(option)) },
                            )
                        }
                    }
                }
            }
            when {
                library.isEmpty -> item {
                    EmptyText("The offline lesson library is still loading. It is bundled with the app, so no connection is needed.")
                }
                sections.isEmpty() -> item {
                    EmptyText(
                        "This topic's notes are not in the bundled library yet. You can still open the full note on the website.",
                    )
                }
                else -> items(sections) { section -> SectionCard(section) }
            }
            library.formulas[slug]?.takeIf { it.isNotEmpty() }?.let { formulas ->
                item { SectionTitle("Formulas") }
                items(formulas.size) { index ->
                    val formula = formulas[index]
                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(formula.name, style = MaterialTheme.typography.titleSmall)
                            Surface(
                                color = MaterialTheme.colorScheme.surfaceVariant,
                                modifier = Modifier.fillMaxWidth(),
                            ) {
                                Text(
                                    formula.plain.ifBlank { formula.latex },
                                    style = MaterialTheme.typography.bodyMedium,
                                    modifier = Modifier
                                        .padding(10.dp)
                                        .horizontalScroll(rememberScrollState()),
                                )
                            }
                            if (formula.meaning.isNotBlank()) {
                                Text(formula.meaning, style = MaterialTheme.typography.bodySmall)
                            }
                            if (formula.application.isNotBlank()) {
                                Text(
                                    "Where it is used: ${formula.application}",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (questions.isNotEmpty()) {
                        Button(
                            onClick = { onPractise(slug) },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text("Practise ${questions.size} question${if (questions.size == 1) "" else "s"} on this topic")
                        }
                    }
                    OutlinedButton(onClick = { store.toggleTopic(slug) }, modifier = Modifier.fillMaxWidth()) {
                        Text(if (store.isCompleted(slug)) "Mark as not done" else "Mark complete")
                    }
                    OutlinedButton(onClick = { openWeb("topics/$slug/") }, modifier = Modifier.fillMaxWidth()) {
                        Text("Open diagrams and extras on the website")
                    }
                    Text(
                        "Notes are built into the app and work offline. The website is only used for interactive diagrams, " +
                            "3D models and the code playground.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.size(4.dp))
                }
            }
        }
    }
}

@Composable
private fun SectionCard(section: LessonSection) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(section.title, style = MaterialTheme.typography.titleMedium)
            }
            if (section.callout.isNotBlank()) {
                val (container, content) = calloutColors(section.callout)
                Surface(color = container, contentColor = content) {
                    Text(
                        section.callout.replaceFirstChar { it.uppercase() },
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
                    )
                }
            }
            BlocksView(section.blocks)
        }
    }
}
