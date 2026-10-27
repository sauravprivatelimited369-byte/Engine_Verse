package io.github.sauravprivatelimited369byte.engineverse.data

import android.content.Context
import android.util.JsonReader
import android.util.JsonToken
import io.github.sauravprivatelimited369byte.engineverse.core.Block
import io.github.sauravprivatelimited369byte.engineverse.core.Formula
import io.github.sauravprivatelimited369byte.engineverse.core.LessonSection
import io.github.sauravprivatelimited369byte.engineverse.core.PracticeOption
import io.github.sauravprivatelimited369byte.engineverse.core.PracticeQuestion
import io.github.sauravprivatelimited369byte.engineverse.core.Span
import io.github.sauravprivatelimited369byte.engineverse.core.TopicNotes
import java.io.IOException

/**
 * Reads the offline lesson library bundled in assets/content.json: full notes at
 * four depths, formulas and the practice bank, generated from the website's seed
 * data by scripts/export_mobile_content.py.
 *
 * The document is about 7 MB. Materialising all of it would take seconds and a
 * large heap, so this repository streams it with [JsonReader]: the practice bank
 * once (cached) and one topic's notes at a time (cached in a small LRU).
 */
object ContentRepository {
    private const val ASSET = "content.json"
    private const val TOPIC_CACHE_SIZE = 6

    @Volatile
    private var practiceCache: List<PracticeQuestion>? = null

    private val topicCache = object : LinkedHashMap<String, TopicNotes>(TOPIC_CACHE_SIZE, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, TopicNotes>): Boolean =
            size > TOPIC_CACHE_SIZE
    }

    /** The whole practice bank, parsed once. Call from a background dispatcher. */
    fun practice(context: Context): List<PracticeQuestion> {
        practiceCache?.let { return it }
        return synchronized(this) {
            practiceCache ?: (stream(context) { reader ->
                var found: List<PracticeQuestion> = emptyList()
                reader.beginObject()
                while (reader.hasNext()) {
                    if (reader.nextName() == "practice") {
                        found = parseQuestions(reader)
                    } else {
                        reader.skipValue()
                    }
                }
                reader.endObject()
                found
            } ?: emptyList()).also { practiceCache = it }
        }
    }

    fun question(context: Context, slug: String): PracticeQuestion? =
        practice(context).firstOrNull { it.slug == slug }

    fun questionCount(context: Context, topic: String): Int =
        if (topic.isBlank()) 0 else practice(context).count { it.topic == topic }

    /** One topic's notes at every depth it has, plus its formulas. */
    fun topicNotes(context: Context, slug: String): TopicNotes {
        if (slug.isBlank()) return TopicNotes(slug, emptyMap(), emptyList())
        synchronized(topicCache) { topicCache[slug] }?.let { return it }
        val loaded = stream(context) { reader ->
            var levels: Map<String, List<LessonSection>> = emptyMap()
            var formulas: List<Formula> = emptyList()
            reader.beginObject()
            while (reader.hasNext()) {
                when (reader.nextName()) {
                    "notes" -> levels = parseNotesFor(reader, slug)
                    "formulas" -> formulas = parseFormulasFor(reader, slug)
                    else -> reader.skipValue()
                }
            }
            reader.endObject()
            TopicNotes(slug, levels, formulas)
        } ?: TopicNotes(slug, emptyMap(), emptyList())
        synchronized(topicCache) { topicCache[slug] = loaded }
        return loaded
    }

    private fun <T> stream(context: Context, body: (JsonReader) -> T): T? = try {
        context.assets.open(ASSET).bufferedReader(Charsets.UTF_8).use { input ->
            JsonReader(input).use { reader -> body(reader) }
        }
    } catch (e: IOException) {
        null
    } catch (e: IllegalStateException) {
        null
    }

    private fun parseNotesFor(reader: JsonReader, wanted: String): Map<String, List<LessonSection>> {
        val levels = mutableMapOf<String, List<LessonSection>>()
        reader.beginObject()
        while (reader.hasNext()) {
            val slug = reader.nextName()
            if (slug != wanted) {
                reader.skipValue()
                continue
            }
            reader.beginObject()
            while (reader.hasNext()) {
                val level = reader.nextName()
                val sections = mutableListOf<LessonSection>()
                reader.beginArray()
                while (reader.hasNext()) {
                    parseSection(reader)?.let { sections += it }
                }
                reader.endArray()
                if (sections.isNotEmpty()) levels[level] = sections
            }
            reader.endObject()
        }
        reader.endObject()
        return levels
    }

    private fun parseFormulasFor(reader: JsonReader, wanted: String): List<Formula> {
        val formulas = mutableListOf<Formula>()
        reader.beginObject()
        while (reader.hasNext()) {
            val slug = reader.nextName()
            if (slug != wanted) {
                reader.skipValue()
                continue
            }
            reader.beginArray()
            while (reader.hasNext()) {
                formulas += parseFormula(reader)
            }
            reader.endArray()
        }
        reader.endObject()
        return formulas
    }

    private fun parseSection(reader: JsonReader): LessonSection? {
        var kind = ""
        var title = ""
        var callout = ""
        var blocks: List<Block> = emptyList()
        reader.beginObject()
        while (reader.hasNext()) {
            when (reader.nextName()) {
                "kind" -> kind = reader.nextString()
                "title" -> title = reader.nextString()
                "callout" -> callout = reader.nextString()
                "blocks" -> blocks = parseBlocks(reader)
                else -> reader.skipValue()
            }
        }
        reader.endObject()
        if (title.isBlank() && blocks.isEmpty()) return null
        return LessonSection(
            kind = kind,
            title = title.ifBlank { "Notes" },
            callout = callout,
            blocks = blocks,
        )
    }

    private fun parseFormula(reader: JsonReader): Formula {
        var name = ""
        var latex = ""
        var plain = ""
        var meaning = ""
        var application = ""
        reader.beginObject()
        while (reader.hasNext()) {
            when (reader.nextName()) {
                "name" -> name = reader.nextString()
                "latex" -> latex = reader.nextString()
                "plain" -> plain = reader.nextString()
                "meaning" -> meaning = reader.nextString()
                "application" -> application = reader.nextString()
                else -> reader.skipValue()
            }
        }
        reader.endObject()
        return Formula(name, latex, plain.ifBlank { latex }, meaning, application)
    }

    private fun parseQuestions(reader: JsonReader): List<PracticeQuestion> {
        val questions = mutableListOf<PracticeQuestion>()
        reader.beginArray()
        while (reader.hasNext()) {
            parseQuestion(reader)?.let { questions += it }
        }
        reader.endArray()
        return questions
    }

    private fun parseQuestion(reader: JsonReader): PracticeQuestion? {
        var slug = ""
        var subject = ""
        var topic = ""
        var difficulty = ""
        var stem: List<Block> = emptyList()
        var context: List<Block> = emptyList()
        var explanation: List<Block> = emptyList()
        val options = mutableListOf<PracticeOption>()
        reader.beginObject()
        while (reader.hasNext()) {
            when (reader.nextName()) {
                "slug" -> slug = reader.nextString()
                "subject" -> subject = reader.nextString()
                "topic" -> topic = reader.nextString()
                "difficulty" -> difficulty = reader.nextString()
                "stem" -> stem = parseBlocks(reader)
                "context" -> context = parseBlocks(reader)
                "explanation" -> explanation = parseBlocks(reader)
                "options" -> {
                    reader.beginArray()
                    while (reader.hasNext()) {
                        options += parseOption(reader)
                    }
                    reader.endArray()
                }
                else -> reader.skipValue()
            }
        }
        reader.endObject()
        if (slug.isBlank() || options.size < 2 || options.none { it.correct }) return null
        return PracticeQuestion(
            slug = slug,
            subject = subject,
            topic = topic,
            difficulty = difficulty,
            stem = stem,
            context = context,
            options = options,
            explanation = explanation,
        )
    }

    private fun parseOption(reader: JsonReader): PracticeOption {
        var label = ""
        var correct = false
        var body: List<Block> = emptyList()
        var why: List<Block> = emptyList()
        reader.beginObject()
        while (reader.hasNext()) {
            when (reader.nextName()) {
                "label" -> label = reader.nextString()
                "correct" -> correct = reader.nextBoolean()
                "body" -> body = parseBlocks(reader)
                "why" -> why = parseBlocks(reader)
                else -> reader.skipValue()
            }
        }
        reader.endObject()
        return PracticeOption(label, body, correct, why)
    }

    private fun parseBlocks(reader: JsonReader): List<Block> {
        val blocks = mutableListOf<Block>()
        reader.beginArray()
        while (reader.hasNext()) {
            parseBlock(reader)?.let { blocks += it }
        }
        reader.endArray()
        return blocks
    }

    private fun parseBlock(reader: JsonReader): Block? {
        reader.beginArray()
        val kind = if (reader.hasNext() && reader.peek() == JsonToken.STRING) reader.nextString() else ""
        var index = 0
        var level = 2
        var first = ""
        var second = ""
        var spans: List<Span> = emptyList()
        var items: List<List<Span>> = emptyList()
        var head: List<List<Span>> = emptyList()
        var rows: List<List<List<Span>>> = emptyList()

        while (reader.hasNext()) {
            index += 1
            when {
                kind == "p" || kind == "quote" -> spans = parseSpans(reader)
                kind == "h" && index == 1 -> level = if (reader.peek() == JsonToken.NUMBER) reader.nextInt() else 2
                kind == "h" -> spans = parseSpans(reader)
                (kind == "ul" || kind == "ol") && index == 1 -> items = parseItems(reader)
                kind == "code" && index == 1 -> first = stringOrSkip(reader)
                kind == "code" -> second = stringOrSkip(reader)
                kind == "math" && index == 1 -> first = stringOrSkip(reader)
                kind == "math" -> second = stringOrSkip(reader)
                kind == "table" && index == 1 -> head = parseItems(reader)
                kind == "table" -> rows = parseRows(reader)
                else -> reader.skipValue()
            }
        }
        reader.endArray()

        return when (kind) {
            "p" -> Block.Paragraph(spans)
            "quote" -> Block.Quote(spans)
            "h" -> Block.Heading(if (level <= 0) 2 else level, spans)
            "ul" -> Block.Bullets(items)
            "ol" -> Block.Numbers(items)
            "code" -> Block.Code(first, second)
            "math" -> Block.Math(first, second.ifBlank { first })
            "table" -> Block.Table(head, rows)
            "hr" -> Block.Rule
            else -> null
        }
    }

    private fun stringOrSkip(reader: JsonReader): String {
        if (reader.peek() == JsonToken.STRING) return reader.nextString()
        reader.skipValue()
        return ""
    }

    private fun parseItems(reader: JsonReader): List<List<Span>> {
        val items = mutableListOf<List<Span>>()
        reader.beginArray()
        while (reader.hasNext()) {
            val runs = parseSpans(reader)
            if (runs.isNotEmpty()) items += runs
        }
        reader.endArray()
        return items
    }

    private fun parseRows(reader: JsonReader): List<List<List<Span>>> {
        val rows = mutableListOf<List<List<Span>>>()
        reader.beginArray()
        while (reader.hasNext()) {
            rows += parseItems(reader)
        }
        reader.endArray()
        return rows
    }

    private fun parseSpans(reader: JsonReader): List<Span> {
        val spans = mutableListOf<Span>()
        reader.beginArray()
        while (reader.hasNext()) {
            var text = ""
            var flags = ""
            reader.beginArray()
            if (reader.hasNext()) text = reader.nextString()
            if (reader.hasNext()) flags = reader.nextString()
            reader.endArray()
            if (text.isEmpty()) continue
            spans += Span(
                text = text,
                bold = flags.contains('b'),
                italic = flags.contains('i'),
                code = flags.contains('c'),
                math = flags.contains('m'),
            )
        }
        reader.endArray()
        return spans
    }
}
