package io.github.sauravprivatelimited369byte.engineverse

import io.github.sauravprivatelimited369byte.engineverse.core.UrlPolicy
import io.github.sauravprivatelimited369byte.engineverse.core.UrlPolicy.Decision
import org.junit.Assert.assertEquals
import org.junit.Test

class UrlPolicyTest {
    private val policy = UrlPolicy("https://sauravprivatelimited369-byte.github.io/Engine_Verse/")

    @Test
    fun sitePagesLoadInTheApp() {
        assertEquals(Decision.LOAD_IN_APP, policy.decide("https://sauravprivatelimited369-byte.github.io/Engine_Verse/"))
        assertEquals(Decision.LOAD_IN_APP, policy.decide("https://sauravprivatelimited369-byte.github.io/Engine_Verse"))
        assertEquals(Decision.LOAD_IN_APP, policy.decide("https://SAURAVPRIVATELIMITED369-BYTE.github.io/Engine_Verse/topics/arrays/#notes"))
        assertEquals(Decision.LOAD_IN_APP, policy.decide("https://sauravprivatelimited369-byte.github.io/Engine_Verse/search/?q=heap"))
    }

    @Test
    fun otherPagesOnTheSameHostOrOtherHostsGoToTheBrowser() {
        assertEquals(Decision.OPEN_EXTERNALLY, policy.decide("https://sauravprivatelimited369-byte.github.io/OtherRepo/"))
        assertEquals(Decision.OPEN_EXTERNALLY, policy.decide("https://sauravprivatelimited369-byte.github.io/Engine_Verse_evil/"))
        assertEquals(Decision.OPEN_EXTERNALLY, policy.decide("https://github.com/sauravprivatelimited369-byte/Engine_Verse"))
        assertEquals(Decision.OPEN_EXTERNALLY, policy.decide("https://sauravprivatelimited369-byte.github.io.evil.example/Engine_Verse/"))
        assertEquals(Decision.OPEN_EXTERNALLY, policy.decide("http://sauravprivatelimited369-byte.github.io/Engine_Verse/"))
        assertEquals(Decision.OPEN_EXTERNALLY, policy.decide("mailto:someone@example.com"))
    }

    @Test
    fun trickyFormsOfTheSiteAreNotTrusted() {
        assertEquals(Decision.OPEN_EXTERNALLY, policy.decide("https://user@sauravprivatelimited369-byte.github.io/Engine_Verse/"))
        assertEquals(Decision.OPEN_EXTERNALLY, policy.decide("https://sauravprivatelimited369-byte.github.io:8443/Engine_Verse/"))
        assertEquals(Decision.OPEN_EXTERNALLY, policy.decide("https://sauravprivatelimited369-byte.github.io/Engine_Verse/../OtherRepo/"))
    }

    @Test
    fun dangerousSchemesAreBlocked() {
        for (url in listOf(
            "javascript:alert(1)",
            "intent://scan/#Intent;scheme=zxing;end",
            "file:///sdcard/secret.txt",
            "content://com.android.contacts/contacts",
            "data:text/html,<script>alert(1)</script>",
            "not a url at all",
            "",
        )) {
            assertEquals(url, Decision.BLOCK, policy.decide(url))
        }
    }

    @Test
    fun pageUrlBuildsOnlyPlainRelativePaths() {
        val home = "https://sauravprivatelimited369-byte.github.io/Engine_Verse/"
        assertEquals(home, policy.home)
        assertEquals(home + "topics/arrays/", policy.pageUrl("topics/arrays/"))
        assertEquals(home + "dpp/", policy.pageUrl("/dpp/"))
        assertEquals(home, policy.pageUrl(""))
        assertEquals(home, policy.pageUrl("../../etc/passwd"))
        assertEquals(home, policy.pageUrl("https://evil.example/"))
        assertEquals(home, policy.pageUrl("topics/<script>/"))
    }
}
