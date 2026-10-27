package io.github.sauravprivatelimited369byte.engineverse.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.sauravprivatelimited369byte.engineverse.core.Block
import io.github.sauravprivatelimited369byte.engineverse.core.Span

/**
 * Renders the blocks produced by scripts/export_mobile_content.py. Both the
 * Android and the Apple app read the same block list, so a note looks the same
 * on every device and needs no Markdown parsing (and no web page) at runtime.
 */
@Composable
fun BlocksView(blocks: List<Block>, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        blocks.forEach { block -> BlockView(block) }
    }
}

@Composable
fun BlockView(block: Block) {
    when (block) {
        is Block.Paragraph -> Text(
            spans(block.spans),
            style = MaterialTheme.typography.bodyMedium,
        )
        is Block.Heading -> Text(
            spans(block.spans),
            style = if (block.level <= 3) {
                MaterialTheme.typography.titleSmall
            } else {
                MaterialTheme.typography.labelLarge
            },
            modifier = Modifier.padding(top = 4.dp),
        )
        is Block.Bullets -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            block.items.forEach { item ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("•", style = MaterialTheme.typography.bodyMedium)
                    Text(spans(item), style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
        is Block.Numbers -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            block.items.forEachIndexed { index, item ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("${index + 1}.", style = MaterialTheme.typography.bodyMedium)
                    Text(spans(item), style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
        is Block.Quote -> Surface(
            color = MaterialTheme.colorScheme.surfaceVariant,
            shape = RoundedCornerShape(10.dp),
        ) {
            Text(
                spans(block.spans),
                style = MaterialTheme.typography.bodyMedium,
                fontStyle = FontStyle.Italic,
                modifier = Modifier.padding(12.dp),
            )
        }
        is Block.Code -> Surface(
            color = MaterialTheme.colorScheme.surfaceVariant,
            shape = RoundedCornerShape(10.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(Modifier.padding(12.dp)) {
                if (block.language.isNotBlank()) {
                    Text(
                        block.language,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Text(
                    block.text,
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                )
            }
        }
        is Block.Math -> Surface(
            color = MaterialTheme.colorScheme.surfaceVariant,
            shape = RoundedCornerShape(10.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                block.plain,
                style = MaterialTheme.typography.bodyMedium,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier
                    .padding(12.dp)
                    .horizontalScroll(rememberScrollState()),
            )
        }
        is Block.Table -> TableView(block)
        Block.Rule -> HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
    }
}

@Composable
private fun TableView(block: Block.Table) {
    val columns = maxOf(block.head.size, block.rows.maxOfOrNull { it.size } ?: 0)
    if (columns == 0) return
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(10.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(vertical = 6.dp)) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp)) {
                repeat(columns) { index ->
                    val cell = block.head.getOrNull(index).orEmpty()
                    Text(
                        spans(cell.map { it.copy(bold = true) }),
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.weight(1f).padding(end = 8.dp),
                    )
                }
            }
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            block.rows.forEach { row ->
                Row(
                    Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.Top,
                ) {
                    repeat(columns) { index ->
                        Text(
                            spans(row.getOrNull(index).orEmpty()),
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.weight(1f).padding(end = 8.dp),
                        )
                    }
                }
            }
        }
    }
}

/** Builds one styled string from a list of spans. */
@Composable
fun spans(spans: List<Span>): AnnotatedString {
    val codeColor = MaterialTheme.colorScheme.onSurfaceVariant
    val codeBackground = MaterialTheme.colorScheme.surfaceVariant
    val mathColor = MaterialTheme.colorScheme.primary
    return remember(spans, codeColor, codeBackground, mathColor) {
        buildAnnotatedString {
            spans.forEach { span ->
                val style = SpanStyle(
                    fontWeight = if (span.bold) FontWeight.Bold else null,
                    fontStyle = if (span.italic) FontStyle.Italic else null,
                    fontFamily = if (span.code || span.math) FontFamily.Monospace else null,
                    fontSize = if (span.code || span.math) 13.sp else TextUnit.Unspecified,
                    color = if (span.math) mathColor else Color.Unspecified,
                    background = if (span.code) codeBackground else Color.Unspecified,
                )
                withStyle(style) { append(span.text) }
            }
        }
    }
}

/** Badge colour for a note section's callout (remember, warning, exam, ...). */
@Composable
fun calloutColors(callout: String): Pair<Color, Color> = when (callout) {
    "remember" -> MaterialTheme.colorScheme.secondaryContainer to MaterialTheme.colorScheme.onSecondaryContainer
    "exam", "warning" -> MaterialTheme.colorScheme.tertiaryContainer to MaterialTheme.colorScheme.onTertiaryContainer
    "interview", "realworld" -> MaterialTheme.colorScheme.primaryContainer to MaterialTheme.colorScheme.onPrimaryContainer
    else -> MaterialTheme.colorScheme.surfaceVariant to MaterialTheme.colorScheme.onSurfaceVariant
}
