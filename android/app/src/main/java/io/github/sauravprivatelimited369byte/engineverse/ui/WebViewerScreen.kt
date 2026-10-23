package io.github.sauravprivatelimited369byte.engineverse.ui

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import io.github.sauravprivatelimited369byte.engineverse.BuildConfig
import io.github.sauravprivatelimited369byte.engineverse.R
import io.github.sauravprivatelimited369byte.engineverse.core.UrlPolicy

/**
 * Shows one page of the EngineVerse website. Hardened rather than a bare
 * WebView: only the site's own HTTPS pages load here (UrlPolicy), other links
 * open in the browser, file and content access are off, no JavaScript bridge
 * is exposed, mixed content and pop-up windows are refused, Safe Browsing is
 * on, and a failed load shows a native offline screen instead of an error page.
 * File inputs (progress and planner imports) open the system file picker; the
 * site cannot save blob downloads here, so its export buttons say so.
 */
@SuppressLint("SetJavaScriptEnabled") // the site's quizzes and playground need it; no bridge is added
@Composable
fun WebViewerScreen(path: String, policy: UrlPolicy, onBack: () -> Unit, openCatalog: () -> Unit) {
    val context = LocalContext.current
    val startUrl = remember(path) { policy.pageUrl(path) }
    var title by remember { mutableStateOf("Forge") }
    var progress by remember { mutableIntStateOf(0) }
    var failed by remember { mutableStateOf(false) }
    var canGoBack by remember { mutableStateOf(false) }

    // <input type="file"> support: the page waits on this callback until the
    // user picks a file (or cancels, which must still be reported as null).
    var pendingFiles by remember { mutableStateOf<ValueCallback<Array<Uri>>?>(null) }
    val filePicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        pendingFiles?.onReceiveValue(if (uri != null) arrayOf(uri) else null)
        pendingFiles = null
    }

    val webView = remember {
        WebView(context).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true // the site keeps progress in localStorage
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.javaScriptCanOpenWindowsAutomatically = false
            settings.setSupportMultipleWindows(false)
            settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            settings.setGeolocationEnabled(false)
            settings.mediaPlaybackRequiresUserGesture = true
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) settings.safeBrowsingEnabled = true
            settings.userAgentString = settings.userAgentString + " EngineVerseAndroid/" + BuildConfig.VERSION_NAME

            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val url = request.url.toString()
                    return when (policy.decide(url)) {
                        UrlPolicy.Decision.LOAD_IN_APP -> false
                        UrlPolicy.Decision.OPEN_EXTERNALLY -> {
                            openExternal(view.context, url)
                            true
                        }
                        UrlPolicy.Decision.BLOCK -> true
                    }
                }

                override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                    failed = false
                }

                override fun onPageFinished(view: WebView, url: String?) {
                    canGoBack = view.canGoBack()
                    view.title?.takeIf { it.isNotBlank() && !it.startsWith("http") }?.let {
                        title = it.substringBefore(" — ").substringBefore(" - ")
                    }
                }

                override fun doUpdateVisitedHistory(view: WebView, url: String?, isReload: Boolean) {
                    canGoBack = view.canGoBack()
                }

                override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                    if (request.isForMainFrame) failed = true
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onProgressChanged(view: WebView, newProgress: Int) {
                    progress = newProgress
                }

                override fun onShowFileChooser(
                    webView: WebView,
                    filePathCallback: ValueCallback<Array<Uri>>,
                    fileChooserParams: FileChooserParams,
                ): Boolean {
                    pendingFiles?.onReceiveValue(null)
                    pendingFiles = filePathCallback
                    return try {
                        // Any type: JSON exports are often labelled octet-stream,
                        // and the page validates what it reads.
                        filePicker.launch("*/*")
                        true
                    } catch (e: ActivityNotFoundException) {
                        pendingFiles = null
                        false
                    }
                }
            }
            // Real file URLs (for example a release download) go to the browser;
            // blob: URLs fail the policy and are ignored.
            setDownloadListener { url, _, _, _, _ ->
                if (policy.decide(url) != UrlPolicy.Decision.BLOCK) openExternal(context, url)
            }
            loadUrl(startUrl)
        }
    }

    DisposableEffect(webView) {
        onDispose {
            webView.stopLoading()
            webView.destroy()
        }
    }

    // System Back walks the page history first, then leaves the viewer.
    BackHandler(enabled = canGoBack && !failed) { webView.goBack() }

    ScreenScaffold(
        title = title,
        onBack = onBack,
        actions = {
            IconButton(onClick = {
                failed = false
                webView.reload()
            }) { Icon(painterResource(R.drawable.ic_refresh), contentDescription = "Reload") }
            IconButton(onClick = { openExternal(context, webView.url ?: startUrl) }) {
                Icon(painterResource(R.drawable.ic_open_in_new), contentDescription = "Open in browser")
            }
        },
    ) { inner ->
        Box(Modifier.fillMaxSize().padding(inner)) {
            AndroidView(factory = { webView }, modifier = Modifier.fillMaxSize())
            if (progress in 1..99 && !failed) {
                LinearProgressIndicator(progress = { progress / 100f }, modifier = Modifier.fillMaxWidth())
            }
            if (failed) {
                OfflineState(
                    online = isOnline(context),
                    onRetry = {
                        failed = false
                        if (webView.url.isNullOrEmpty()) webView.loadUrl(startUrl) else webView.reload()
                    },
                    openCatalog = openCatalog,
                )
            }
        }
    }
}

@Composable
private fun OfflineState(online: Boolean, onRetry: () -> Unit, openCatalog: () -> Unit) {
    Column(
        Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).padding(32.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(
            painterResource(R.drawable.ic_offline),
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(48.dp),
        )
        Text(
            if (online) "This page did not load" else "You are offline",
            style = MaterialTheme.typography.titleLarge,
            textAlign = TextAlign.Center,
        )
        Text(
            if (online) "The website did not respond. Try again in a moment."
            else "Full notes and the playground need a connection. The subject catalogue, your progress and the planner work offline.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        Button(onClick = onRetry) { Text("Try again") }
        OutlinedButton(onClick = openCatalog) { Text("Open offline catalogue") }
    }
}
