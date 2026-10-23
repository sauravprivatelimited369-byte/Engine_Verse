package io.github.sauravprivatelimited369byte.engineverse.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import io.github.sauravprivatelimited369byte.engineverse.data.ThemeMode

// The website's palette (backend/static/css/app.css, "Meridian Glass"):
// burnt-ember primary on warm paper in light mode, molten ember on warm
// near-black in dark mode. The light primary is the fixed burnt ember
// (#B44A0C) the website uses for link ink — a brighter orange fails contrast
// on paper; the dark primary is lightened ember (#FFB067) for the same reason.
private val LightColors = lightColorScheme(
    primary = Color(0xFF1D5BD6),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFDCE7FB),
    onPrimaryContainer = Color(0xFF0A2660),
    secondary = Color(0xFF0C3C8F),
    onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFE3E9F6),
    onSecondaryContainer = Color(0xFF071F49),
    tertiary = Color(0xFF147A49),
    tertiaryContainer = Color(0xFFD8F1E4),
    onTertiaryContainer = Color(0xFF00391F),
    background = Color(0xFFF5F2EA),
    onBackground = Color(0xFF10243D),
    surface = Color(0xFFFBF9F4),
    onSurface = Color(0xFF10243D),
    surfaceVariant = Color(0xFFE8E4D9),
    onSurfaceVariant = Color(0xFF3B4A5E),
    surfaceContainer = Color(0xFFFBF9F4),
    surfaceContainerHigh = Color(0xFFF2EEE4),
    outline = Color(0xFF5F6A78),
    outlineVariant = Color(0xFFD5D0C4),
    error = Color(0xFFB3261E),
    errorContainer = Color(0xFFFCE4E2),
    onErrorContainer = Color(0xFF5F1410),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF5C95F5),
    onPrimary = Color(0xFF05121F),
    primaryContainer = Color(0xFF1D3B66),
    onPrimaryContainer = Color(0xFFDCE7FB),
    secondary = Color(0xFFA9C8FF),
    onSecondary = Color(0xFF071F49),
    secondaryContainer = Color(0xFF0C2A55),
    onSecondaryContainer = Color(0xFFE3E9F6),
    tertiary = Color(0xFF4ECF92),
    tertiaryContainer = Color(0xFF0C4F37),
    onTertiaryContainer = Color(0xFFD8F1E4),
    background = Color(0xFF0A1522),
    onBackground = Color(0xFFEDF2F8),
    surface = Color(0xFF101F30),
    onSurface = Color(0xFFEDF2F8),
    surfaceVariant = Color(0xFF1A2C40),
    onSurfaceVariant = Color(0xFFC3CFDD),
    surfaceContainer = Color(0xFF101F30),
    surfaceContainerHigh = Color(0xFF16283C),
    outline = Color(0xFF98A6B7),
    outlineVariant = Color(0xFF2A3B50),
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
fun MeridianTheme(dark: Boolean, content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (dark) DarkColors else LightColors, content = content)
}
