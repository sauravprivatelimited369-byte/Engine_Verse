package io.github.sauravprivatelimited369byte.engineverse.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import io.github.sauravprivatelimited369byte.engineverse.data.ThemeMode

// The website's palette (backend/static/css/app.css): indigo accent on a cool
// grey canvas in light mode, near-black navy in dark mode.
private val LightColors = lightColorScheme(
    primary = Color(0xFF3F5BF0),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFDFE5FF),
    onPrimaryContainer = Color(0xFF0B1A66),
    secondary = Color(0xFF6B4FD8),
    onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFEAE3FF),
    onSecondaryContainer = Color(0xFF26145F),
    tertiary = Color(0xFF117A55),
    tertiaryContainer = Color(0xFFD5F5E6),
    onTertiaryContainer = Color(0xFF00391F),
    background = Color(0xFFF3F5FA),
    onBackground = Color(0xFF111827),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF111827),
    surfaceVariant = Color(0xFFE8EBF3),
    onSurfaceVariant = Color(0xFF475069),
    surfaceContainer = Color(0xFFFFFFFF),
    surfaceContainerHigh = Color(0xFFF7F8FC),
    outline = Color(0xFF8A93A8),
    outlineVariant = Color(0xFFD5DAE5),
    error = Color(0xFFB3261E),
    errorContainer = Color(0xFFFCE4E2),
    onErrorContainer = Color(0xFF5F1410),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFA3B4FF),
    onPrimary = Color(0xFF0B1A66),
    primaryContainer = Color(0xFF2B3D9E),
    onPrimaryContainer = Color(0xFFDFE5FF),
    secondary = Color(0xFFC6B6FF),
    onSecondary = Color(0xFF26145F),
    secondaryContainer = Color(0xFF3F2C8C),
    onSecondaryContainer = Color(0xFFEAE3FF),
    tertiary = Color(0xFF7FDDB3),
    tertiaryContainer = Color(0xFF0C4F37),
    onTertiaryContainer = Color(0xFFD5F5E6),
    background = Color(0xFF070B14),
    onBackground = Color(0xFFE6E9F2),
    surface = Color(0xFF0E1422),
    onSurface = Color(0xFFE6E9F2),
    surfaceVariant = Color(0xFF1A2236),
    onSurfaceVariant = Color(0xFFB4BCD0),
    surfaceContainer = Color(0xFF111827),
    surfaceContainerHigh = Color(0xFF161E30),
    outline = Color(0xFF6B7489),
    outlineVariant = Color(0xFF2A3348),
    error = Color(0xFFF2B8B5),
    errorContainer = Color(0xFF601410),
    onErrorContainer = Color(0xFFFCE4E2),
)

@Composable
fun isDarkTheme(mode: ThemeMode): Boolean = when (mode) {
    ThemeMode.SYSTEM -> isSystemInDarkTheme()
    ThemeMode.LIGHT -> false
    ThemeMode.DARK -> true
}

@Composable
fun EngineVerseTheme(dark: Boolean, content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (dark) DarkColors else LightColors, content = content)
}
