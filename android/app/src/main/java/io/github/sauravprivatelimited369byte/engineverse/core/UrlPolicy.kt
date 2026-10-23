package io.github.sauravprivatelimited369byte.engineverse.core

import java.net.URI
import java.net.URISyntaxException

/**
 * Decides where a URL may open. Only pages of the EngineVerse website (one
 * HTTPS origin and its base path) load inside the app; ordinary web links go
 * to the user's browser; every other scheme (intent:, javascript:, file:,
 * content:, data: ...) is refused so a page cannot reach into the device.
 */
class UrlPolicy(siteUrl: String) {
    enum class Decision { LOAD_IN_APP, OPEN_EXTERNALLY, BLOCK }

    private val site: URI = URI(siteUrl)
    private val host: String = requireNotNull(site.host) { "site URL needs a host" }.lowercase()
    private val basePath: String = site.path.orEmpty().let { if (it.endsWith("/")) it else "$it/" }

    /** The site's home page, always ending in a slash. */
    val home: String = "https://$host$basePath"

    fun decide(url: String): Decision {
        val uri = try {
            URI(url.trim())
        } catch (e: URISyntaxException) {
            return Decision.BLOCK
        }
        return when (uri.scheme?.lowercase()) {
            "https" -> if (isSitePage(uri)) Decision.LOAD_IN_APP else Decision.OPEN_EXTERNALLY
            "http", "mailto" -> Decision.OPEN_EXTERNALLY
            else -> Decision.BLOCK
        }
    }

    private fun isSitePage(uri: URI): Boolean {
        if (uri.host?.lowercase() != host) return false
        if (uri.port != -1 && uri.port != 443) return false
        if (uri.rawUserInfo != null) return false
        val path = uri.normalize().rawPath.orEmpty()
        if (path.contains("..")) return false
        return path == basePath.removeSuffix("/") || path.startsWith(basePath)
    }

    /**
     * Builds the absolute URL of a page from a site-relative path such as
     * "topics/arrays/". Anything that is not a plain relative path falls back
     * to the home page rather than being trusted.
     */
    fun pageUrl(path: String): String {
        val clean = path.trim().trimStart('/')
        if (clean.isEmpty()) return home
        if (!SAFE_PATH.matches(clean) || clean.contains("..")) return home
        return home + clean
    }

    private companion object {
        val SAFE_PATH = Regex("^[A-Za-z0-9._~/-]+$")
    }
}
