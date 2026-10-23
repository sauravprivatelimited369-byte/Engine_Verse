package io.github.sauravprivatelimited369byte.engineverse.core

import java.util.TimeZone

/** Study streaks over "epoch days" (days since 1970-01-01 in local time). */
object Streak {
    data class Result(val current: Int, val longest: Int)

    private const val DAY_MS = 86_400_000L

    fun today(nowMillis: Long = System.currentTimeMillis(), zone: TimeZone = TimeZone.getDefault()): Long =
        Math.floorDiv(nowMillis + zone.getOffset(nowMillis), DAY_MS)

    /**
     * The current streak counts back from today, or from yesterday when today
     * has no activity yet (the streak is not lost until a whole day passes).
     */
    fun compute(days: Collection<Long>, today: Long): Result {
        if (days.isEmpty()) return Result(0, 0)
        val sorted = days.toSortedSet()
        var longest = 0
        var run = 0
        var previous: Long? = null
        for (day in sorted) {
            run = if (previous != null && day == previous + 1) run + 1 else 1
            if (run > longest) longest = run
            previous = day
        }
        var cursor = when {
            today in sorted -> today
            (today - 1) in sorted -> today - 1
            else -> return Result(0, longest)
        }
        var current = 0
        while (cursor in sorted) {
            current++
            cursor--
        }
        return Result(current, longest)
    }
}
