package org.safeflight.android.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.NavigationRailItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.safeflight.android.ui.theme.SfColors
import org.safeflight.android.video.VideoController

enum class Screen(val label: String, val glyph: String) {
    FLIGHT("Vuelo", "✈"),
    CONNECTION("Conexión", "⇄"),
    MISSIONS("Misiones", "☰"),
}

@Composable
fun SafeFlightRoot(
    viewModel: MainViewModel,
    video: VideoController,
    onRestartVideo: () -> Unit,
    onStopVideo: () -> Unit,
) {
    var screen by rememberSaveable { mutableStateOf(Screen.FLIGHT) }
    val snackbar = remember { SnackbarHostState() }
    val message by viewModel.message.collectAsStateWithLifecycle()
    LaunchedEffect(message) {
        message?.let {
            snackbar.showSnackbar(it)
            viewModel.consumeMessage()
        }
    }

    Scaffold(
        containerColor = SfColors.Background,
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        Row(Modifier.fillMaxSize().padding(padding)) {
            NavigationRail(containerColor = SfColors.Surface) {
                Screen.entries.forEach { item ->
                    NavigationRailItem(
                        selected = screen == item,
                        onClick = { screen = item },
                        icon = { Text(item.glyph, fontSize = 20.sp) },
                        label = { Text(item.label, fontWeight = FontWeight.SemiBold) },
                        colors = NavigationRailItemDefaults.colors(
                            selectedTextColor = SfColors.Accent,
                            unselectedTextColor = SfColors.Muted,
                            selectedIconColor = SfColors.Text,
                            unselectedIconColor = SfColors.Muted,
                            indicatorColor = SfColors.SurfaceHigh,
                        ),
                    )
                }
            }
            Box(Modifier.fillMaxSize()) {
                when (screen) {
                    Screen.FLIGHT -> FlightScreen(viewModel, video)
                    Screen.CONNECTION -> ConnectionScreen(viewModel, video, onRestartVideo, onStopVideo)
                    Screen.MISSIONS -> MissionsScreen(viewModel)
                }
            }
        }
    }
}
