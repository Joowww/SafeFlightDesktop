package org.safeflight.android.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

object SfColors {
    val Background = Color(0xFF0E1116)
    val Surface = Color(0xFF171B22)
    val SurfaceHigh = Color(0xFF212733)
    val Outline = Color(0xFF323A48)
    val Text = Color(0xFFE8ECF2)
    val Muted = Color(0xFF8C96A8)
    val Accent = Color(0xFF3B8ED0)
    val Ok = Color(0xFF4ADE80)
    val Warn = Color(0xFFF0B429)
    val Danger = Color(0xFFFB7185)
    val Locked = Color(0xFF5B6373)
}

private val scheme = darkColorScheme(
    primary = SfColors.Accent,
    onPrimary = Color.White,
    background = SfColors.Background,
    onBackground = SfColors.Text,
    surface = SfColors.Surface,
    onSurface = SfColors.Text,
    surfaceVariant = SfColors.SurfaceHigh,
    onSurfaceVariant = SfColors.Muted,
    outline = SfColors.Outline,
    error = SfColors.Danger,
)

@Composable
fun SafeFlightTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = scheme, content = content)
}
