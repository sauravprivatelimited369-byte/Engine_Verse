package io.github.sauravprivatelimited369byte.engineverse

import io.github.sauravprivatelimited369byte.engineverse.core.Catalog
import io.github.sauravprivatelimited369byte.engineverse.core.CatalogSearch
import io.github.sauravprivatelimited369byte.engineverse.core.Subject
import io.github.sauravprivatelimited369byte.engineverse.core.Topic
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class CatalogSearchTest {
    private fun topic(slug: String, title: String, tags: List<String> = emptyList()) =
        Topic(slug, title, "", "medium", 30, tags, true)

    private val subjects = listOf(
        Subject("dsa", "Data Structures", "CS201", "Computer Science", "Arrays, lists and trees",
            listOf(topic("arrays", "Arrays"), topic("heaps", "Heaps & Priority Queues", listOf("heap")))),
        Subject("thermo", "Thermodynamics", "ME202", "Mechanical", "Energy and entropy",
            listOf(topic("first-law", "First Law"))),
        Subject("cpp", "Programming in C++", "CS102", "First year", "Language basics", emptyList()),
    )

    @Test
    fun blankQueryReturnsEverything() {
        assertEquals(3, CatalogSearch.filter(subjects, "  ").size)
    }

    @Test
    fun matchesNamesCodesGroupsTopicsAndTags() {
        assertEquals(listOf("thermo"), CatalogSearch.filter(subjects, "entropy").map { it.slug })
        assertEquals(listOf("dsa"), CatalogSearch.filter(subjects, "cs201").map { it.slug })
        assertEquals(listOf("dsa"), CatalogSearch.filter(subjects, "priority queue").map { it.slug })
        assertEquals(listOf("thermo"), CatalogSearch.filter(subjects, "MECHANICAL").map { it.slug })
        assertEquals(listOf("cpp"), CatalogSearch.filter(subjects, "c++").map { it.slug })
    }

    @Test
    fun everyWordMustMatch() {
        assertEquals(emptyList<String>(), CatalogSearch.filter(subjects, "arrays entropy").map { it.slug })
    }

    @Test
    fun catalogLooksUpTopicsWithTheirSubject() {
        val catalog = Catalog(subjects)
        assertEquals(3, catalog.topicCount)
        assertEquals("dsa", catalog.topic("heaps")?.first?.slug)
        assertNull(catalog.topic("missing"))
        assertNull(catalog.subject("missing"))
    }
}
