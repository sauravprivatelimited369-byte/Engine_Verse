@file:OptIn(ExperimentalMaterial3Api::class)

package io.github.sauravprivatelimited369byte.engineverse.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
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
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import io.github.sauravprivatelimited369byte.engineverse.R
import io.github.sauravprivatelimited369byte.engineverse.core.Catalog
import io.github.sauravprivatelimited369byte.engineverse.core.LessonLibrary
import io.github.sauravprivatelimited369byte.engineverse.core.PracticeQuestion
import io.github.sauravprivatelimited369byte.engineverse.data.AppStore

/**
 * The practice bank is bundled with the app: 500+ multiple-choice questions
 * across the same subjects, answerable with no connection. Answers and
 * explanations are on the device, and what you have answered is kept locally.
 */
@Composable
fun PracticeScreen(
    store: AppStore,
    catalog: Catalog,
    library: LessonLibrary,
    topicFilter: String?,
    openQuestion: (String) -> Unit,
    clearTopicFilter: () -> Unit,
) {
    var query by rememberSaveable { mutableStateOf("") }
    val all = remember(library, topicFilter) {
        if (topicFilter.isNullOrBlank()) library.questions else library.questionsForTopic(topicFilter)
    }
    val visible = remember(all, query) {
        val needle = query.trim().lowercase()
        if (needle.isEmpty()) {
            all
        } else {
            all.filter { question ->
                question.headline.lowercase().contains(needle) ||
                    question.topic.contains(needle) ||
                    question.subject.contains(needle) ||
                    catalog.topic(question.topic)?.second?.title?.lowercase()?.contains(needle) == true
            }
        }
    }
    val topicName = topicFilter?.let { slug -> catalog.topic(slug)?.second?.title }
    val topicCounts = remember(library) { library.questions.groupingBy { it.topic }.eachCount() }

    ScreenScaffold(title = if (topicName != null) "Practice: $topicName" else "Practice") { inner ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(inner),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(
                            "${store.answeredCount} answered · ${store.correctCount} correct",
                            style = MaterialTheme.typography.titleMedium,
                        )
                        Text(
                            "${library.questions.size} questions are built into the app and work offline.",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }
            if (topicName != null) {
                item {
                    OutlinedButton(onClick = clearTopicFilter) {
                        Text("Showing this topic only. Show all questions")
                    }
                }
            }
            item {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it.take(60) },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    label = { Text("Search questions") },
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
            if (library.isEmpty) {
                item { EmptyText("The offline question bank is still loading. It is bundled with the app.") }
            } else if (visible.isEmpty()) {
                item { EmptyText("No question matches \"$query\".") }
            }
            items(visible, key = { it.slug }) { question ->
                QuestionRow(store, catalog, question, topicCounts[question.topic] ?: 0) {
                    openQuestion(question.slug)
                }
            }
        }
    }
}

@Composable
private fun QuestionRow(
    store: AppStore,
    catalog: Catalog,
    question: PracticeQuestion,
    topicQuestionCount: Int,
    onClick: () -> Unit,
) {
    val answered = store.isAnswered(question.slug)
    val correct = store.wasCorrect(question.slug)
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(question.headline, style = MaterialTheme.typography.bodyLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Tag(question.difficulty)
                val topicTitle = catalog.topic(question.topic)?.second?.title
                if (topicTitle != null) Tag(topicTitle)
                when {
                    correct -> Tag("Correct", MaterialTheme.colorScheme.tertiaryContainer, MaterialTheme.colorScheme.onTertiaryContainer)
                    answered -> Tag("Missed", MaterialTheme.colorScheme.errorContainer, MaterialTheme.colorScheme.onErrorContainer)
                    else -> Tag("New")
                }
            }
            if (topicQuestionCount > 1) {
                Text(
                    "$topicQuestionCount questions on this topic",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
fun QuestionScreen(
    store: AppStore,
    catalog: Catalog,
    library: LessonLibrary,
    slug: String,
    onBack: () -> Unit,
    openQuestion: (String) -> Unit,
    openNotes: (String) -> Unit,
) {
    val question = library.question(slug)
    val title = question?.let { catalog.topic(it.topic)?.second?.title } ?: "Question"
    var chosen by rememberSaveable(slug) { mutableStateOf("") }
    var checked by rememberSaveable(slug) { mutableStateOf(false) }

    ScreenScaffold(title = title, onBack = onBack) { inner ->
        if (question == null) {
            Column(Modifier.padding(inner).padding(16.dp)) {
                EmptyText("This question is not in the bundled bank.")
            }
            return@ScreenScaffold
        }
        val correctOption = question.options.firstOrNull { it.correct }
        val isRight = chosen.isNotEmpty() && question.options.firstOrNull { it.label == chosen }?.correct == true
        val next = library.questions.let { list ->
            val index = list.indexOfFirst { it.slug == question.slug }
            if (index >= 0 && index + 1 < list.size) list[index + 1] else null
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(inner),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Tag(question.difficulty)
                    catalog.topic(question.topic)?.second?.title?.let { Tag(it) }
                }
            }
            item { BlocksView(question.stem) }
            if (question.context.isNotEmpty()) {
                item {
                    Surface(
                        color = MaterialTheme.colorScheme.surfaceVariant,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Column(Modifier.padding(12.dp)) { BlocksView(question.context) }
                    }
                }
            }
            items(question.options, key = { it.label }) { option ->
                val selected = chosen == option.label
                val showCorrect = checked && option.correct
                val showWrong = checked && selected && !option.correct
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = when {
                            showCorrect -> MaterialTheme.colorScheme.tertiaryContainer
                            showWrong -> MaterialTheme.colorScheme.errorContainer
                            selected -> MaterialTheme.colorScheme.primaryContainer
                            else -> MaterialTheme.colorScheme.surface
                        },
                    ),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable(enabled = !checked) { chosen = option.label },
                ) {
                    Row(Modifier.padding(14.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("${option.label}.", style = MaterialTheme.typography.titleSmall)
                        BlocksView(option.body, Modifier.weight(1f))
                    }
                }
            }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (!checked) {
                        Button(
                            onClick = {
                                if (chosen.isNotEmpty()) {
                                    checked = true
                                    store.answer(question.slug, isRight)
                                }
                            },
                            enabled = chosen.isNotEmpty(),
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text("Check answer")
                        }
                    } else {
                        Card(
                            colors = CardDefaults.cardColors(
                                containerColor = if (isRight) {
                                    MaterialTheme.colorScheme.tertiaryContainer
                                } else {
                                    MaterialTheme.colorScheme.errorContainer
                                },
                            ),
                        ) {
                            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(
                                    if (isRight) "Correct" else "Not quite — the answer is ${correctOption?.label ?: "not shown"}",
                                    style = MaterialTheme.typography.titleSmall,
                                )
                                BlocksView(question.explanation)
                            }
                        }
                        OutlinedButton(
                            onClick = {
                                chosen = ""
                                checked = false
                            },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text("Try this question again")
                        }
                        if (next != null) {
                            Button(onClick = { openQuestion(next.slug) }, modifier = Modifier.fillMaxWidth()) {
                                Text("Next question")
                            }
                        }
                        OutlinedButton(onClick = { openNotes(question.topic) }, modifier = Modifier.fillMaxWidth()) {
                            Text("Read the notes for this topic")
                        }
                    }
                }
            }
        }
    }
}
