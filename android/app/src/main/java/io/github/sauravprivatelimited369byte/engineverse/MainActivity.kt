package io.github.sauravprivatelimited369byte.engineverse

import android.graphics.Color
import android.os.Bundle
import android.webkit.WebView
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.lifecycleScope
import io.github.sauravprivatelimited369byte.engineverse.core.Catalog
import io.github.sauravprivatelimited369byte.engineverse.core.UrlPolicy
import io.github.sauravprivatelimited369byte.engineverse.data.AppStore
import io.github.sauravprivatelimited369byte.engineverse.data.CatalogRepository
import io.github.sauravprivatelimited369byte.engineverse.ui.ForgeApp
import io.github.sauravprivatelimited369byte.engineverse.ui.theme.ForgeTheme
import io.github.sauravprivatelimited369byte.engineverse.ui.theme.isDarkTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private var catalog by mutableStateOf<Catalog?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        val splash = installSplashScreen()
        super.onCreate(savedInstanceState)
        // The splash stays until the bundled catalogue is parsed (a few ms).
        splash.setKeepOnScreenCondition { catalog == null }
        lifecycleScope.launch {
            catalog = withContext(Dispatchers.IO) { CatalogRepository.load(applicationContext) }
        }
        // Remote debugging of the in-app web viewer only in debug builds.
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        enableEdgeToEdge()

        val store = AppStore.get(applicationContext)
        val policy = UrlPolicy(BuildConfig.SITE_URL)
        setContent {
            val dark = isDarkTheme(store.themeMode)
            // Status/navigation bar icons follow the app theme, not only the system one.
            DisposableEffect(dark) {
                enableEdgeToEdge(
                    statusBarStyle = if (dark) {
                        SystemBarStyle.dark(Color.TRANSPARENT)
                    } else {
                        SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT)
                    },
                    navigationBarStyle = if (dark) {
                        SystemBarStyle.dark(Color.TRANSPARENT)
                    } else {
                        SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT)
                    },
                )
                onDispose {}
            }
            ForgeTheme(dark) {
                ForgeApp(store, catalog ?: Catalog.EMPTY, policy)
            }
        }
    }
}
