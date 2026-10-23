package io.github.sauravprivatelimited369byte.engineverse.data

import android.content.Context
import io.github.sauravprivatelimited369byte.engineverse.core.Catalog
import io.github.sauravprivatelimited369byte.engineverse.core.Subject
import io.github.sauravprivatelimited369byte.engineverse.core.Topic
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException

/**
 * Reads the subject and topic catalogue bundled in assets/catalog.json. The
 * file is generated from the website's seed data by
 * scripts/export_android_catalog.py, so it works with no connection.
 */
object CatalogRepository {
    private const val ASSET = "catalog.json"

    fun load(context: Context): Catalog = try {
        val text = context.assets.open(ASSET).bufferedReader(Charsets.UTF_8).use { it.readText() }
        parse(JSONObject(text))
    } catch (e: IOException) {
        Catalog.EMPTY
    } catch (e: JSONException) {
        Catalog.EMPTY
    }

    private fun parse(root: JSONObject): Catalog {
        val subjects = root.optJSONArray("subjects") ?: JSONArray()
        return Catalog(
            (0 until subjects.length()).mapNotNull { i ->
                val s = subjects.optJSONObject(i) ?: return@mapNotNull null
                val topics = s.optJSONArray("topics") ?: JSONArray()
                Subject(
                    slug = s.optString("slug"),
                    name = s.optString("name"),
                    code = s.optString("code"),
                    group = s.optString("group"),
                    description = s.optString("description"),
                    topics = (0 until topics.length()).mapNotNull { j ->
                        val t = topics.optJSONObject(j) ?: return@mapNotNull null
                        val tags = t.optJSONArray("tags") ?: JSONArray()
                        Topic(
                            slug = t.optString("slug"),
                            title = t.optString("title"),
                            summary = t.optString("summary"),
                            difficulty = t.optString("difficulty"),
                            minutes = t.optInt("minutes"),
                            tags = (0 until tags.length()).map { k -> tags.optString(k) },
                            reviewed = t.optBoolean("reviewed"),
                        )
                    }.filter { it.slug.isNotBlank() },
                )
            }.filter { it.slug.isNotBlank() },
        )
    }
}
