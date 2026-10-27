@file:OptIn(ExperimentalLayoutApi::class)

package io.github.sauravprivatelimited369byte.engineverse.ui

import android.net.Uri
import androidx.annotation.DrawableRes
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import io.github.sauravprivatelimited369byte.engineverse.R
import io.github.sauravprivatelimited369byte.engineverse.core.Catalog
import io.github.sauravprivatelimited369byte.engineverse.core.UrlPolicy
import io.github.sauravprivatelimited369byte.engineverse.data.AppStore

object Routes {
    const val HOME = "home"
    const val LEARN = "learn"
    const val PRACTICE = "practice"
    const val PLAYGROUND = "playground"
    const val PLANNER = "planner"
    const val PORTFOLIO = "portfolio"
    const val SETTINGS = "settings"
    const val SUBJECT = "subject/{slug}"
    const val TOPIC = "topic/{slug}"
    const val PRACTICE_TOPIC = "practice-topic/{slug}"
    const val NOTES = "notes/{slug}?level={level}"
    const val QUESTION = "question/{slug}"
    const val WEB = "web?path={path}"

    fun subject(slug: String) = "subject/${Uri.encode(slug)}"
    fun topic(slug: String) = "topic/${Uri.encode(slug)}"
    fun notes(slug: String, level: String = "") = "notes/${Uri.encode(slug)}?level=${Uri.encode(level)}"
    fun practiceForTopic(slug: String) = "practice-topic/${Uri.encode(slug)}"
    fun question(slug: String) = "question/${Uri.encode(slug)}"
    fun web(path: String) = "web?path=${Uri.encode(path)}"
}

private data class Tab(val route: String, val label: String, @DrawableRes val icon: Int)

private val TABS = listOf(
    Tab(Routes.HOME, "Home", R.drawable.ic_home),
    Tab(Routes.LEARN, "Learn", R.drawable.ic_book),
    Tab(Routes.PRACTICE, "Practice", R.drawable.ic_quiz),
    Tab(Routes.PLANNER, "Planner", R.drawable.ic_calendar),
    Tab(Routes.PORTFOLIO, "Record", R.drawable.ic_person),
)

@Composable
fun MeridianApp(
    store: AppStore,
    catalog: Catalog,
    policy: UrlPolicy,
) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val current = entry?.destination?.route
    val openWeb: (String) -> Unit = { path -> nav.navigate(Routes.web(path)) }
    val go: (String) -> Unit = { route -> nav.navigate(route) }
    val back: () -> Unit = { nav.popBackStack() }
    val openQuestion: (String) -> Unit = { slug -> nav.navigate(Routes.question(slug)) }
    val openNotes: (String, String) -> Unit = { slug, level -> nav.navigate(Routes.notes(slug, level)) }

    Scaffold(
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            if (TABS.any { it.route == current }) {
                NavigationBar {
                    TABS.forEach { tab ->
                        NavigationBarItem(
                            selected = current == tab.route,
                            onClick = {
                                nav.navigate(tab.route) {
                                    popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(painterResource(tab.icon), contentDescription = null) },
                            label = { Text(tab.label) },
                        )
                    }
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = nav,
            startDestination = Routes.HOME,
            modifier = Modifier.padding(padding).consumeWindowInsets(padding),
        ) {
            composable(Routes.HOME) {
                HomeScreen(store, catalog, navigate = go, openWeb = openWeb, openNotes = openNotes)
            }
            composable(Routes.LEARN) {
                LearnScreen(store, catalog, openSubject = { go(Routes.subject(it)) })
            }
            composable(Routes.PRACTICE) {
                PracticeScreen(
                    store = store,
                    catalog = catalog,
                    topicFilter = null,
                    openQuestion = openQuestion,
                    clearTopicFilter = {},
                )
            }
            composable(
                Routes.PRACTICE_TOPIC,
                arguments = listOf(navArgument("slug") { type = NavType.StringType }),
            ) { e ->
                PracticeScreen(
                    store = store,
                    catalog = catalog,
                    topicFilter = e.arguments?.getString("slug").orEmpty(),
                    openQuestion = openQuestion,
                    clearTopicFilter = {
                        nav.navigate(Routes.PRACTICE) {
                            popUpTo(nav.graph.findStartDestination().id)
                            launchSingleTop = true
                        }
                    },
                )
            }
            composable(Routes.PLAYGROUND) { PlaygroundScreen(openWeb = openWeb) }
            composable(Routes.PLANNER) { PlannerScreen(store) }
            composable(Routes.PORTFOLIO) {
                PortfolioScreen(store, catalog, openTopic = { go(Routes.topic(it)) })
            }
            composable(Routes.SETTINGS) { SettingsScreen(store, onBack = back, openWeb = openWeb) }
            composable(Routes.SUBJECT, arguments = listOf(navArgument("slug") { type = NavType.StringType })) { e ->
                SubjectScreen(
                    store = store,
                    catalog = catalog,
                    slug = e.arguments?.getString("slug").orEmpty(),
                    onBack = back,
                    openTopic = { go(Routes.topic(it)) },
                )
            }
            composable(Routes.TOPIC, arguments = listOf(navArgument("slug") { type = NavType.StringType })) { e ->
                TopicScreen(
                    store = store,
                    catalog = catalog,
                    slug = e.arguments?.getString("slug").orEmpty(),
                    onBack = back,
                    openNotes = { level -> openNotes(e.arguments?.getString("slug").orEmpty(), level) },
                    openPractise = { slug -> go(Routes.practiceForTopic(slug)) },
                    openWeb = openWeb,
                )
            }
            composable(
                Routes.NOTES,
                arguments = listOf(
                    navArgument("slug") { type = NavType.StringType },
                    navArgument("level") {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                ),
            ) { e ->
                val slug = e.arguments?.getString("slug").orEmpty()
                NotesScreen(
                    store = store,
                    catalog = catalog,
                    slug = slug,
                    initialLevel = e.arguments?.getString("level").orEmpty(),
                    onBack = back,
                    onPractise = { topic -> go(Routes.practiceForTopic(topic)) },
                    openWeb = openWeb,
                )
            }
            composable(Routes.QUESTION, arguments = listOf(navArgument("slug") { type = NavType.StringType })) { e ->
                QuestionScreen(
                    store = store,
                    catalog = catalog,
                    slug = e.arguments?.getString("slug").orEmpty(),
                    onBack = back,
                    openQuestion = openQuestion,
                    openNotes = { topic -> openNotes(topic, "") },
                )
            }
            composable(
                Routes.WEB,
                arguments = listOf(navArgument("path") {
                    type = NavType.StringType
                    defaultValue = ""
                }),
            ) { e ->
                WebViewerScreen(
                    path = e.arguments?.getString("path").orEmpty(),
                    policy = policy,
                    onBack = back,
                    openCatalog = {
                        nav.navigate(Routes.LEARN) {
                            popUpTo(nav.graph.findStartDestination().id)
                            launchSingleTop = true
                        }
                    },
                )
            }
        }
    }
}
