package io.github.sauravprivatelimited369byte.engineverse

import io.github.sauravprivatelimited369byte.engineverse.core.PlannerRules
import io.github.sauravprivatelimited369byte.engineverse.core.PlannerTask
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Test

class PlannerRulesTest {
    private fun task(id: String, due: Long?, done: Boolean = false, created: Long = 0) =
        PlannerTask(id, "Task $id", due, done, created)

    @Test
    fun titlesAreTrimmedCollapsedAndCapped() {
        assertEquals("Read heaps", PlannerRules.cleanTitle("  Read \n  heaps  "))
        assertNull(PlannerRules.cleanTitle("   "))
        assertEquals(PlannerRules.MAX_TITLE, PlannerRules.cleanTitle("x".repeat(500))!!.length)
    }

    @Test
    fun blankTitlesAndAFullPlannerAddNothing() {
        val empty = emptyList<PlannerTask>()
        assertSame(empty, PlannerRules.add(empty, "  ", null, "a", 1))
        val full = (1..PlannerRules.MAX_TASKS).map { task("$it", null) }
        assertSame(full, PlannerRules.add(full, "One more", null, "z", 1))
        assertEquals(1, PlannerRules.add(empty, "Revise DBMS", 5, "a", 1).size)
    }

    @Test
    fun openTasksComeFirstBySoonestDueThenFinishedNewestFirst() {
        val tasks = listOf(
            task("undated", null, created = 1),
            task("later", 20, created = 2),
            task("soon", 10, created = 3),
            task("doneOld", 5, done = true, created = 4),
            task("doneNew", 5, done = true, created = 9),
        )
        assertEquals(listOf("soon", "later", "undated", "doneNew", "doneOld"), PlannerRules.sorted(tasks).map { it.id })
        assertEquals("soon", PlannerRules.nextUp(tasks)?.id)
    }

    @Test
    fun toggleRemoveAndClear() {
        val tasks = listOf(task("a", null), task("b", null))
        val toggled = PlannerRules.toggle(tasks, "a")
        assertEquals(true, toggled.first { it.id == "a" }.done)
        assertEquals(listOf("b"), PlannerRules.remove(tasks, "a").map { it.id })
        assertEquals(listOf("b"), PlannerRules.clearDone(toggled).map { it.id })
    }

    @Test
    fun dueLabels() {
        assertNull(PlannerRules.dueLabel(null, 100))
        assertEquals("Overdue", PlannerRules.dueLabel(99, 100))
        assertEquals("Due today", PlannerRules.dueLabel(100, 100))
        assertEquals("Due tomorrow", PlannerRules.dueLabel(101, 100))
        assertEquals("Due in 7 days", PlannerRules.dueLabel(107, 100))
    }
}
