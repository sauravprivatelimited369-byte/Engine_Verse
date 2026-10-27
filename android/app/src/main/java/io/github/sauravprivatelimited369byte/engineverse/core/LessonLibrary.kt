package io.github.sauravprivatelimited369byte.engineverse.core

/**
 * A piece of inline text inside a note or question, already resolved from
 * Markdown by scripts/export_mobile_content.py. The apps never parse Markdown
 * at runtime: they only lay these spans out, so both platforms render the same
 * words identically.
 */
data class Span(
    val text: String,
    val bold: Boolean = false,
    val italic: Boolean = false,
    val code: Boolean = false,
    val math: Boolean = false,
)

/** A block of a note section or question. Mirrors the exporter's block list. */
sealed interface Block {
    data class Paragraph(val spans: List<Span>) : Block
    data class Heading(val level: Int, val spans: List<Span>) : Block
    data class Bullets(val items: List<List<Span>>) : Block
    data class Numbers(val items: List<List<Span>>) : Block
    data class Quote(val spans: List<Span>) : Block
    data class Code(val text: String, val language: String) : Block
    /** [plain] is a readable form of [latex] for display; [latex] is kept for copying. */
    data class Math(val latex: String, val plain: String) : Block
    data class Table(val head: List<List<Span>>, val rows: List<List<List<Span>>>) : Block
    data object Rule : Block
}

/** One of the thirteen note sections (definition, formula, derivation, ...). */
data class LessonSection(
    val kind: String,
    val title: String,
    val callout: String,
    val blocks: List<Block>,
)

data class Formula(
    val name: String,
    val latex: String,
    val plain: String,
    val meaning: String,
    val application: String,
)

data class PracticeOption(
    val label: String,
    val body: List<Block>,
    val correct: Boolean,
    val why: List<Block>,
)

data class PracticeQuestion(
    val slug: String,
    val subject: String,
    val topic: String,
    val difficulty: String,
    val stem: List<Block>,
    val context: List<Block>,
    val options: List<PracticeOption>,
    val explanation: List<Block>,
) {
    /** The first paragraph of the stem, for lists and headers. */
    val headline: String
        get() = stem.filterIsInstance<Block.Paragraph>().firstOrNull()
            ?.spans?.joinToString(" ") { it.text }
            ?.take(160)
            ?: slug
}

/**
 * One topic's notes: every depth it was written at, plus its formulas.
 *
 * The bundled library is one 7 MB document. Parsing it whole at launch would
 * cost seconds and a large heap on a modest phone, so the repository streams it
 * and materialises only the topic a student opens (see ContentRepository).
 */
data class TopicNotes(
    val slug: String,
    val levels: Map<String, List<LessonSection>>,
    val formulas: List<Formula>,
) {
    val isEmpty: Boolean get() = levels.isEmpty()

    /** Depths that exist for this topic, in reading order. */
    val availableLevels: List<String> get() = NoteLevel.ORDER.filter { levels.containsKey(it) }

    fun sections(level: String): List<LessonSection> = levels[level].orEmpty()
}

/** The four note depths, in the order the website offers them. */
object NoteLevel {
    val ORDER = listOf("beginner", "standard", "advanced", "industry")

    fun name(level: String): String = when (level) {
        "beginner" -> "Beginner"
        "standard" -> "Standard"
        "advanced" -> "Advanced"
        "industry" -> "Industry"
        else -> level.replaceFirstChar { it.uppercase() }
    }
}
