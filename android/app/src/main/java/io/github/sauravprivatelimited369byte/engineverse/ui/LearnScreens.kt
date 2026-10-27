@file:OptIn(ExperimentalMaterial3Api::class)

package io.github.sauravprivatelimited369byte.engineverse.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import io.github.sauravprivatelimited369byte.engineverse.R
import io.github.sauravprivatelimited369byte.engineverse.core.Catalog
import io.github.sauravprivatelimited369byte.engineverse.core.LessonLibrary
import io.github.sauravprivatelimited369byte.engineverse.core.CatalogSearch
import io.github.sauravprivatelimited369byte.engineverse.core.Subject
import io.github.sauravprivatelimited369byte.engineverse.data.AppStore

@Composable
fun LearnScreen(store: AppStore, catalog: Catalog, openSubject: (String) -> Unit) {
    var query by rememberSaveable { mutableStateOf("") }
    val results = remember(query, catalog) { CatalogSearch.filter(catalog.subjects, query) }

    ScreenScaffold(title = "Subjects") { inner ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(inner),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it.take(80) },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    label = { Text("Search subjects and topics") },
                    leadingIcon = { Icon(painterResource(R.drawable.ic_search), contentDescription = null) },
                    trailingIcon = {
                        if (query.isNotEmpty()) {
                            IconButton(onClick = { query = "" }) {
                                Icon(painterResource(R.drawable.ic_close), contentDescription = "Clear search")
                            }
                        }
                    },
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                )
            }
            item {
                Text(
                    if (query.isBlank()) "${catalog.subjects.size} subjects, available offline"
                    else "${results.size} of ${catalog.subjects.size} subjects match",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (catalog.subjects.isEmpty()) {
                item { EmptyText("The bundled catalogue could not be read. Reinstalling the app restores it.") }
            } else if (results.isEmpty()) {
                item { EmptyText("Nothing matches \"$query\". Try a shorter word, a subject code or a topic name.") }
            }
            items(results, key = { it.slug }) { subject ->
                SubjectCard(subject, done = subject.topics.count { store.isCompleted(it.slug) }) { openSubject(subject.slug) }
            }
        }
    }
}

@Composable
private fun SubjectCard(subject: Subject, done: Int, onClick: () -> Unit) {
    val total = subject.topics.size
    Card(
        onClick = onClick,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(subject.name, style = MaterialTheme.typography.titleMedium)
            Text(
                listOf(subject.code, subject.group, "$total topics").filter { it.isNotBlank() }.joinToString(" · "),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (total > 0) {
                LinearProgressIndicator(
                    progress = { done.toFloat() / total },
                    modifier = Modifier.fillMaxWidth().semantics { contentDescription = "$done of $total topics done" },
                )
            }
        }
    }
}

@Composable
fun SubjectScreen(store: AppStore, catalog: Catalog, slug: String, onBack: () -> Unit, openTopic: (String) -> Unit) {
    val subject = catalog.subject(slug)
    ScreenScaffold(title = subject?.name ?: "Subject", onBack = onBack) { inner ->
        if (subject == null) {
            Column(Modifier.padding(inner).padding(16.dp)) { EmptyText("This subject is not in the bundled catalogue.") }
            return@ScreenScaffold
        }
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(inner),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            item {
                Text(subject.description, style = MaterialTheme.typography.bodyMedium)
                Spacer(Modifier.size(12.dp))
                SectionTitle("Topics")
            }
            items(subject.topics, key = { it.slug }) { topic ->
                val done = store.isCompleted(topic.slug)
                Row(
                    Modifier.fillMaxWidth().clickable { openTopic(topic.slug) }.padding(vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(
                        painterResource(R.drawable.ic_check),
                        contentDescription = if (done) "Completed" else null,
                        tint = if (done) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.outlineVariant,
                    )
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(topic.title, style = MaterialTheme.typography.bodyLarge)
                        Text(
                            "${topic.difficulty} · ${topic.minutes} min",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            }
        }
    }
}

@Composable
fun TopicScreen(
    store: AppStore,
    catalog: Catalog,
    library: LessonLibrary,
    slug: String,
    onBack: () -> Unit,
    openNotes: (String) -> Unit,
    openPractise: (String) -> Unit,
    openWeb: (String) -> Unit,
) {
    val entry = catalog.topic(slug)
    ScreenScaffold(title = entry?.second?.title ?: "Topic", onBack = onBack) { inner ->
        if (entry == null) {
            Column(Modifier.padding(inner).padding(16.dp)) { EmptyText("This topic is not in the bundled catalogue.") }
            return@ScreenScaffold
        }
        val (subject, topic) = entry
        val done = store.isCompleted(topic.slug)
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(inner),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Text(subject.name, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                Text(topic.title, style = MaterialTheme.typography.headlineSmall)
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Tag(topic.difficulty)
                    Tag("${topic.minutes} min")
                    if (done) {
                        Tag("Completed", MaterialTheme.colorScheme.tertiaryContainer, MaterialTheme.colorScheme.onTertiaryContainer)
                    }
                }
            }
            item { Text(topic.summary, style = MaterialTheme.typography.bodyLarge) }
            if (topic.tags.isNotEmpty()) {
                item {
                    Text(
                        "Covers: " + topic.tags.joinToString(", "),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (!topic.reviewed) {
                item {
                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                        Text(
                            "Public learning draft: this note has not completed editorial review. Check exam-critical " +
                                "details against your course material.",
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.padding(14.dp),
                        )
                    }
                }
            }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    val questionCount = library.questionsForTopic(topic.slug).size
                    Button(onClick = { openNotes("") }, modifier = Modifier.fillMaxWidth()) {
                        Text("Read the notes")
                    }
                    if (questionCount > 0) {
                        OutlinedButton(onClick = { openPractise(topic.slug) }, modifier = Modifier.fillMaxWidth()) {
                            Text("Practise $questionCount question${if (questionCount == 1) "" else "s"}")
                        }
                    }
                    OutlinedButton(onClick = { store.toggleTopic(topic.slug) }, modifier = Modifier.fillMaxWidth()) {
                        Text(if (done) "Mark as not done" else "Mark complete")
                    }
                    OutlinedButton(onClick = { openWeb("topics/${topic.slug}/") }, modifier = Modifier.fillMaxWidth()) {
                        Text("Open diagrams on the website")
                    }
                    Text(
                        "The notes and practice questions are built into the app and work offline; your completion " +
                            "and answers stay on this phone.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
fun EmptyText(text: String) {
    Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
}
