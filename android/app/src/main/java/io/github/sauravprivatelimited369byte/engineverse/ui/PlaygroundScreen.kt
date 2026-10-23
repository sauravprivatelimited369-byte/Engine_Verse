package io.github.sauravprivatelimited369byte.engineverse.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.github.sauravprivatelimited369byte.engineverse.R

/**
 * The playground itself is the website's: each language runs on its real
 * interpreter or compiler built for WebAssembly, inside a worker. This screen
 * says so plainly and opens those pages in the in-app viewer.
 */
@Composable
fun PlaygroundScreen(openWeb: (String) -> Unit) {
    ScreenScaffold(title = "Code playground") { inner ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(inner),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Text(
                        "Code runs on the website's in-browser runtimes (WebAssembly in a separate worker), shown here " +
                            "in the app. Each language downloads its runtime the first time you run it, so you need a " +
                            "connection; a runaway program is stopped by the time limit. Nothing is sent to a server " +
                            "to execute. Each page lists which languages it can run before you start.",
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(16.dp),
                    )
                }
            }
            item {
                ActionCard(R.drawable.ic_code, "CodeLab", "Editor with a separate mode for each language", { openWeb("codelab/") })
            }
            item {
                ActionCard(R.drawable.ic_code, "Code compiler", "Run a single file with input", { openWeb("compiler/") })
            }
            item {
                ActionCard(R.drawable.ic_code, "Python compiler", "CPython in the browser (Pyodide)", { openWeb("python-compiler/") })
            }
            item {
                ActionCard(R.drawable.ic_book, "Coding problems", "Judged problems with hidden tests", { openWeb("practice/problems/") })
            }
        }
    }
}
