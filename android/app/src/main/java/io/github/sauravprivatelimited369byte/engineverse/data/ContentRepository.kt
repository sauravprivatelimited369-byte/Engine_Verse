package io.github.sauravprivatelimited369byte.engineverse.data

import android.content.Context
import io.github.sauravprivatelimited369byte.engineverse.core.Block
import io.github.sauravprivatelimited369byte.engineverse.core.Formula
import io.github.sauravprivatelimited369byte.engineverse.core.LessonLibrary
import io.github.sauravprivatelimited369byte.engineverse.core.LessonSection
import io.github.sauravprivatelimited369byte.engineverse.core.PracticeOption
import io.github.sauravprivatelimited369byte.engineverse.core.PracticeQuestion
import io.github.sauravprivatelimited369byte.engineverse.core.Span
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException

/**
 * Reads the offline lesson library bundled in assets/content.json: full notes at
 * four depths, formulas and the practice bank. The file is generated from the
 * website's seed data by scripts/export_mobile_content.py, so reading and
 * practising work with no connection and no website.
 */
object ContentRepository {
    private const val ASSET = "content.json"

    @Volatile
    private var cached: LessonLibrary? = null

    /** Parsed once and kept; call from a background dispatcher. */
    fun load(context: Context): LessonLibrary {
        cached?.let { return it }
        return synchronized(this) {
            cached ?: parseOrEmpty(context).also { cached = it }
        }
    }

    private fun parseOrEmpty(context: Context): LessonLibrary = try {
        val text = context.assets.open(ASSET).bufferedReader(Charsets.UTF_8).use { it.readText() }
        parse(JSONObject(text))
    } catch (e: IOException) {
        LessonLibrary.EMPTY
    } catch (e: JSONException) {
        LessonLibrary.EMPTY
    } catch (e: OutOfMemoryError) {
        LessonLibrary.EMPTY
    }

    private fun parse(root: JSONObject): LessonLibrary {
        val levels = root.optJSONArray("levels")?.let { array ->
            (0 until array.length()).mapNotNull { i -> array.optString(i).takeIf { it.isNotBlank() } }
        }.orEmpty().ifEmpty { listOf("beginner", "standard", "advanced", "industry") }

        val notes = mutableMapOf<String, Map<String, List<LessonSection>>>()
        root.optJSONObject("notes")?.let { topicObject ->
            topicObject.keys().forEach { topicSlug ->
                val byLevel = topicObject.optJSONObject(topicSlug) ?: return@forEach
                val parsed = mutableMapOf<String, List<LessonSection>>()
                byLevel.keys().forEach { level ->
                    val sections = byLevel.optJSONArray(level) ?: return@forEach
                    parsed[level] = (0 until sections.length()).mapNotNull { i ->
                        parseSection(sections.optJSONObject(i) ?: return@mapNotNull null)
                    }
                }
                notes[topicSlug] = parsed
            }
        }

        val formulas = mutableMapOf<String, List<Formula>>()
        root.optJSONObject("formulas")?.let { formulaObject ->
            formulaObject.keys().forEach { topicSlug ->
                val array = formulaObject.optJSONArray(topicSlug) ?: return@forEach
                formulas[topicSlug] = (0 until array.length()).mapNotNull { i ->
                    val o = array.optJSONObject(i) ?: return@mapNotNull null
                    Formula(
                        name = o.optString("name"),
                        latex = o.optString("latex"),
                        plain = o.optString("latex"),
                        meaning = o.optString("meaning"),
                        application = o.optString("application"),
                    )
                }
            }
        }

        val questions = mutableListOf<PracticeQuestion>()
        root.optJSONArray("practice")?.let { array ->
            for (i in 0 until array.length()) {
                val o = array.optJSONObject(i) ?: continue
                val options = mutableListOf<PracticeOption>()
                val optionArray = o.optJSONArray("options") ?: JSONArray()
                for (j in 0 until optionArray.length()) {
                    val option = optionArray.optJSONObject(j) ?: continue
                    options += PracticeOption(
                        label = option.optString("label"),
                        body = parseBlocks(option.optJSONArray("body")),
                        correct = option.optBoolean("correct"),
                        why = parseBlocks(option.optJSONArray("why")),
                    )
                }
                if (options.size < 2 || options.none { it.correct }) continue
                questions += PracticeQuestion(
                    slug = o.optString("slug"),
                    subject = o.optString("subject"),
                    topic = o.optString("topic"),
                    difficulty = o.optString("difficulty"),
                    stem = parseBlocks(o.optJSONArray("stem")),
                    context = parseBlocks(o.optJSONArray("context")),
                    options = options,
                    explanation = parseBlocks(o.optJSONArray("explanation")),
                )
            }
        }

        return LessonLibrary(levels, notes, formulas, questions)
    }

    private fun parseSection(o: JSONObject): LessonSection? {
        val title = o.optString("title")
        val blocks = parseBlocks(o.optJSONArray("blocks"))
        if (title.isBlank() && blocks.isEmpty()) return null
        return LessonSection(
            kind = o.optString("kind"),
            title = title.ifBlank { "Notes" },
            callout = o.optString("callout"),
            blocks = blocks,
        )
    }

    private fun parseBlocks(array: JSONArray?): List<Block> {
        if (array == null) return emptyList()
        val blocks = mutableListOf<Block>()
        for (i in 0 until array.length()) {
            val raw = array.optJSONArray(i) ?: continue
            when (raw.optString(0)) {
                "p" -> blocks += Block.Paragraph(parseSpans(raw.optJSONArray(1)))
                "h" -> blocks += Block.Heading(raw.optInt(1, 2), parseSpans(raw.optJSONArray(2)))
                "quote" -> blocks += Block.Quote(parseSpans(raw.optJSONArray(1)))
                "ul" -> blocks += Block.Bullets(parseItems(raw.optJSONArray(1)))
                "ol" -> blocks += Block.Numbers(parseItems(raw.optJSONArray(1)))
                "code" -> blocks += Block.Code(raw.optString(1), raw.optString(2))
                "math" -> {
                    val latex = raw.optString(1)
                    val plain = raw.optString(2).ifBlank { latex }
                    blocks += Block.Math(latex, plain)
                }
                "table" -> blocks += Block.Table(
                    head = parseSpansRow(raw.optJSONArray(1)),
                    rows = raw.optJSONArray(2)?.let { rows ->
                        (0 until rows.length()).map { r -> parseSpansRow(rows.optJSONArray(r)) }
                    }.orEmpty(),
                )
                "hr" -> blocks += Block.Rule
            }
        }
        return blocks
    }

    private fun parseItems(array: JSONArray?): List<List<Span>> {
        if (array == null) return emptyList()
        return (0 until array.length()).mapNotNull { i ->
            parseSpans(array.optJSONArray(i)).takeIf { it.isNotEmpty() }
        }
    }

    private fun parseSpansRow(array: JSONArray?): List<List<Span>> {
        if (array == null) return emptyList()
        return (0 until array.length()).map { i -> parseSpans(array.optJSONArray(i)) }
    }

    private fun parseSpans(array: JSONArray?): List<Span> {
        if (array == null) return emptyList()
        val spans = mutableListOf<Span>()
        for (i in 0 until array.length()) {
            val run = array.optJSONArray(i) ?: continue
            val text = run.optString(0)
            if (text.isEmpty()) continue
            val flags = run.optString(1)
            spans += Span(
                text = text,
                bold = flags.contains('b'),
                italic = flags.contains('i'),
                code = flags.contains('c'),
                math = flags.contains('m'),
            )
        }
        return spans
    }
}
