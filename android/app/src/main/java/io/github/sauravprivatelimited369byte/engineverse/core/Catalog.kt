package io.github.sauravprivatelimited369byte.engineverse.core

data class Topic(
    val slug: String,
    val title: String,
    val summary: String,
    val difficulty: String,
    val minutes: Int,
    val tags: List<String>,
    /** False for public drafts that have not completed editorial review. */
    val reviewed: Boolean,
)

data class Subject(
    val slug: String,
    val name: String,
    val code: String,
    val group: String,
    val description: String,
    val topics: List<Topic>,
)

class Catalog(val subjects: List<Subject>) {
    private val topicIndex: Map<String, Pair<Subject, Topic>> =
        subjects.flatMap { s -> s.topics.map { t -> t.slug to (s to t) } }.toMap()
    private val subjectIndex: Map<String, Subject> = subjects.associateBy { it.slug }

    val topicCount: Int get() = topicIndex.size

    fun subject(slug: String): Subject? = subjectIndex[slug]
    fun topic(slug: String): Pair<Subject, Topic>? = topicIndex[slug]

    companion object {
        val EMPTY = Catalog(emptyList())
    }
}

object CatalogSearch {
    fun normalize(text: String): String = text.lowercase().replace(Regex("[^a-z0-9+#]+"), " ").trim()

    /** Subjects whose name, code, group, description, topic titles or tags contain every query word. */
    fun filter(subjects: List<Subject>, query: String): List<Subject> {
        val words = normalize(query).split(' ').filter { it.isNotEmpty() }
        if (words.isEmpty()) return subjects
        return subjects.filter { subject ->
            val haystack = normalize(
                buildString {
                    append(subject.name).append(' ').append(subject.code).append(' ')
                    append(subject.group).append(' ').append(subject.description)
                    subject.topics.forEach { topic ->
                        append(' ').append(topic.title)
                        topic.tags.forEach { append(' ').append(it) }
                    }
                },
            )
            words.all { haystack.contains(it) }
        }
    }
}
