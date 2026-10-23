package io.github.sauravprivatelimited369byte.engineverse.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import io.github.sauravprivatelimited369byte.engineverse.data.ThemeMode

// The website's palette (backend/static/css/app.css, "Obsidian Forge"):
// burnt-ember primary on warm paper in light mode, molten ember on warm
// near-black in dark mode. The light primary is the fixed burnt ember
// (#B44A0C) the website uses for link ink — a brighter orange fails contrast
// on paper; the dark primary is lightened ember (#FFB067) for the same reason.
private val LightColors = lightColorScheme(
    primary = Color(0xFFB44A0C),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFFFE9D6),
    onPrimaryContainer = Color(0xFF431D02),
    secondary = Color(0xFFBE123C),
    onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFFFE3EA),
    onSecondaryContainer = Color(0xFF4A0214),
    tertiary = Color(0xFF117A55),
    tertiaryContainer = Color(0xFFD5F5E6),
    onTertiaryContainer = Color(0xFF00391F),
    background = Color(0xFFFAF6F0),
    onBackground = Color(0xFF211710),
    surface = Color(0xFFFFFDF9),
    onSurface = Color(0xFF211710),
    surfaceVariant = Color(0xFFF1E4D3),
    onSurfaceVariant = Color(0xFF5C4A36),
    surfaceContainer = Color(0xFFFFFDF9),
    surfaceContainerHigh = Color(0xFFFBF7F1),
    outline = Color(0xFF8A7358),
    outlineVariant = Color(0xFFDECFBB),
    error = Color(0xFFB3261E),
    errorContainer = Color(0xFFFCE4E2),
    onErrorContainer = Color(0xFF5F1410),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFFFB067),
    onPrimary = Color(0xFF431D02),
    primaryContainer = Color(0xFF7C3A0E),
    onPrimaryContainer = Color(0xFFFFE9D6),
    secondary = Color(0xFFF9A8C4),
    onSecondary = Color(0xFF4A0214),
    secondaryContainer = Color(0xFF7F1D3A),
    onSecondaryContainer = Color(0xFFFFE3EA),
    tertiary = Color(0xFF7FDDB3),
    tertiaryContainer = Color(0xFF0C4F37),
    onTertiaryContainer = Color(0xFFD5F5E6),
    background = Color(0xFF0B0908),
    onBackground = Color(0xFFF7EFE6),
    surface = Color(0xFF171310),
    onSurface = Color(0xFFF7EFE6),
    surfaceVariant = Color(0xFF241C15),
    onSurfaceVariant = Color(0xFFCBB79E),
    surfaceContainer = Color(0xFF171310),
    surfaceContainerHigh = Color(0xFF1E1712),
    outline = Color(0xFF7A6750),
    outlineVariant = Color(0xFF332920),
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
fun ForgeTheme(dark: Boolean, content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (dark) DarkColors else LightColors, content = content)
}
