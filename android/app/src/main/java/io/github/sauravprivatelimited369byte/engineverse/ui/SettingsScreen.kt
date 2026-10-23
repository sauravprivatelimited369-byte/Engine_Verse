package io.github.sauravprivatelimited369byte.engineverse.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import io.github.sauravprivatelimited369byte.engineverse.BuildConfig
import io.github.sauravprivatelimited369byte.engineverse.R
import io.github.sauravprivatelimited369byte.engineverse.data.AppStore
import io.github.sauravprivatelimited369byte.engineverse.data.ThemeMode

@Composable
fun SettingsScreen(store: AppStore, onBack: () -> Unit, openWeb: (String) -> Unit) {
    val context = LocalContext.current
    var confirmDelete by rememberSaveable { mutableStateOf(false) }

    ScreenScaffold(title = "Settings", onBack = onBack) { inner ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(inner),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                SettingsCard("Appearance") {
                    Column(Modifier.selectableGroup()) {
                        listOf(ThemeMode.SYSTEM to "Follow system", ThemeMode.LIGHT to "Light", ThemeMode.DARK to "Dark")
                            .forEach { (mode, label) ->
                                Row(
                                    Modifier.fillMaxWidth()
                                        .selectable(selected = store.themeMode == mode, onClick = { store.setTheme(mode) }, role = Role.RadioButton)
                                        .padding(vertical = 8.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    RadioButton(selected = store.themeMode == mode, onClick = null)
                                    Text(label, modifier = Modifier.padding(start = 12.dp))
                                }
                            }
                    }
                }
            }
            item {
                SettingsCard("Your data") {
                    Text(
                        "There is no account. Completed topics, your streak and planner tasks are stored only in this " +
                            "app on this phone (and in your own Android backup if you use one). Nothing is uploaded and " +
                            "there is no analytics. Pages you open from the website load from GitHub Pages; that site " +
                            "keeps its own progress in its own storage.",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    OutlinedButton(onClick = { confirmDelete = true }) { Text("Delete all app data") }
                }
            }
            item {
                SettingsCard("About") {
                    Text("EngineVerse ${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.bodyLarge)
                    Text("Open source under the MIT licence.", style = MaterialTheme.typography.bodyMedium)
                    ActionCard(R.drawable.ic_open_in_new, "Source code", "GitHub repository", { openExternal(context, BuildConfig.REPO_URL) })
                    ActionCard(R.drawable.ic_open_in_new, "Report a problem", "Open an issue on GitHub", { openExternal(context, BuildConfig.REPO_URL + "/issues") })
                    ActionCard(R.drawable.ic_home, "Privacy", "How the website handles data", { openWeb("privacy/") })
                }
            }
        }
    }

    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("Delete all app data?") },
            text = { Text("This removes completed topics, your streak, planner tasks and settings from this app. It cannot be undone.") },
            confirmButton = {
                TextButton(onClick = {
                    store.clearAll()
                    confirmDelete = false
                }) { Text("Delete") }
            },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun SettingsCard(title: String, content: @Composable () -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            SectionTitle(title)
            content()
        }
    }
}
