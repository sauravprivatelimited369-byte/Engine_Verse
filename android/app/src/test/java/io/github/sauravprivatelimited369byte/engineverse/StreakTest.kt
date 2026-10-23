package io.github.sauravprivatelimited369byte.engineverse

import io.github.sauravprivatelimited369byte.engineverse.core.Streak
import org.junit.Assert.assertEquals
import org.junit.Test
import java.util.TimeZone

class StreakTest {
    @Test
    fun emptyHistoryHasNoStreak() {
        assertEquals(Streak.Result(0, 0), Streak.compute(emptyList(), 100))
    }

    @Test
    fun streakCountsBackFromToday() {
        assertEquals(Streak.Result(3, 3), Streak.compute(listOf(98L, 99L, 100L), 100))
    }

    @Test
    fun streakSurvivesUntilAWholeDayIsMissed() {
        assertEquals(Streak.Result(2, 2), Streak.compute(listOf(98L, 99L), 100))
        assertEquals(Streak.Result(0, 2), Streak.compute(listOf(97L, 98L), 100))
    }

    @Test
    fun longestRunIsKeptAfterABreak() {
        val days = listOf(10L, 11L, 12L, 13L, 20L, 99L, 100L)
        assertEquals(Streak.Result(2, 4), Streak.compute(days, 100))
    }

    @Test
    fun duplicateDaysCountOnce() {
        assertEquals(Streak.Result(2, 2), Streak.compute(listOf(99L, 99L, 100L, 100L), 100))
    }

    @Test
    fun todayUsesLocalTime() {
        // 2026-10-22T20:00Z is already 23 October in India (UTC+05:30).
        val millis = 1_792_699_200_000L
        val utc = Streak.today(millis, TimeZone.getTimeZone("UTC"))
        val india = Streak.today(millis, TimeZone.getTimeZone("Asia/Kolkata"))
        assertEquals(utc + 1, india)
    }
}
