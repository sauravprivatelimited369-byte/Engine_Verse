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
    const val PLAYGROUND = "playground"
    const val PLANNER = "planner"
    const val PORTFOLIO = "portfolio"
    const val SETTINGS = "settings"
    const val SUBJECT = "subject/{slug}"
    const val TOPIC = "topic/{slug}"
    const val WEB = "web?path={path}"

    fun subject(slug: String) = "subject/${Uri.encode(slug)}"
    fun topic(slug: String) = "topic/${Uri.encode(slug)}"
    fun web(path: String) = "web?path=${Uri.encode(path)}"
}

private data class Tab(val route: String, val label: String, @DrawableRes val icon: Int)

private val TABS = listOf(
    Tab(Routes.HOME, "Home", R.drawable.ic_home),
    Tab(Routes.LEARN, "Learn", R.drawable.ic_book),
    Tab(Routes.PLAYGROUND, "Code", R.drawable.ic_code),
    Tab(Routes.PLANNER, "Planner", R.drawable.ic_calendar),
    Tab(Routes.PORTFOLIO, "Record", R.drawable.ic_person),
)

@Composable
fun ForgeApp(store: AppStore, catalog: Catalog, policy: UrlPolicy) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val current = entry?.destination?.route
    val openWeb: (String) -> Unit = { path -> nav.navigate(Routes.web(path)) }
    val go: (String) -> Unit = { route -> nav.navigate(route) }
    val back: () -> Unit = { nav.popBackStack() }

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
                HomeScreen(store, catalog, navigate = go, openWeb = openWeb)
            }
            composable(Routes.LEARN) {
                LearnScreen(store, catalog, openSubject = { go(Routes.subject(it)) })
            }
            composable(Routes.PLAYGROUND) { PlaygroundScreen(openWeb = openWeb) }
            composable(Routes.PLANNER) { PlannerScreen(store) }
            composable(Routes.PORTFOLIO) {
                PortfolioScreen(store, catalog, openTopic = { go(Routes.topic(it)) })
            }
            composable(Routes.SETTINGS) { SettingsScreen(store, onBack = back, openWeb = openWeb) }
            composable(Routes.SUBJECT, arguments = listOf(navArgument("slug") { type = NavType.StringType })) { e ->
                SubjectScreen(store, catalog, e.arguments?.getString("slug").orEmpty(), onBack = back, openTopic = { go(Routes.topic(it)) })
            }
            composable(Routes.TOPIC, arguments = listOf(navArgument("slug") { type = NavType.StringType })) { e ->
                TopicScreen(store, catalog, e.arguments?.getString("slug").orEmpty(), onBack = back, openWeb = openWeb)
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
