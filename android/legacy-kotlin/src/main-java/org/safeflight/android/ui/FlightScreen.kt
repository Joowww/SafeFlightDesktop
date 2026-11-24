package org.safeflight.android.ui

import androidx.annotation.OptIn
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import org.safeflight.android.control.FlightCommand
import org.safeflight.android.state.LinkStatus
import org.safeflight.android.state.TelemetryReducer
import org.safeflight.android.ui.theme.SfColors
import org.safeflight.android.video.VideoController
import org.safeflight.android.video.VideoStatus

@Composable
fun FlightScreen(viewModel: MainViewModel, video: VideoController) {
    val telemetry by viewModel.telemetry.collectAsStateWithLifecycle()
    val link by viewModel.link.collectAsStateWithLifecycle()
    val videoState by video.state.collectAsStateWithLifecycle()

    Row(Modifier.fillMaxSize().padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        // --- Main video -------------------------------------------------
        Box(
            Modifier.weight(1f).fillMaxHeight()
                .background(Color.Black, RoundedCornerShape(10.dp)),
        ) {
            VideoSurface(video)
            if (videoState.status != VideoStatus.PLAYING) {
                Text(
                    videoLabel(videoState.status) + (videoState.lastError?.let { "\n$it" } ?: ""),
                    color = videoColor(videoState.status),
                    fontSize = 14.sp,
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                )
            }
            Column(Modifier.align(Alignment.TopStart).padding(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                StatusChip(
                    "MAVLINK " + linkLabel(link.status),
                    linkColor(link.status),
                    link.heartbeatAgeMs?.let { "HB ${fmt(it / 1000.0, 1, " s")}" },
                )
                StatusChip(
                    videoLabel(videoState.status),
                    videoColor(videoState.status),
                    videoState.lastFrameAgeMs?.let { "${it} ms" },
                )
            }
            Column(Modifier.align(Alignment.TopEnd).padding(8.dp), horizontalAlignment = Alignment.End) {
                val armedText = when (telemetry.armed) { true -> "ARMADO"; false -> "DESARMADO"; null -> "ARMADO: $UNKNOWN" }
                val current = link.status == LinkStatus.CONNECTED
                val armedColor = when {
                    !current -> SfColors.Muted
                    telemetry.armed == true -> SfColors.Danger
                    telemetry.armed == false -> SfColors.Ok
                    else -> SfColors.Muted
                }
                // Last known values are greyed out and labelled while the link is not current.
                StatusChip(armedText, armedColor, if (!current && telemetry.armed != null) "último" else null)
                Spacer(Modifier.height(6.dp))
                StatusChip(
                    "MODO ${telemetry.flightMode ?: UNKNOWN}",
                    if (current) SfColors.Accent else SfColors.Muted,
                    if (!current && telemetry.flightMode != null) "último" else null,
                )
            }
            if (link.status == LinkStatus.LOST || link.status == LinkStatus.STALE) {
                Text(
                    if (link.status == LinkStatus.LOST) "PÉRDIDA DE TELEMETRÍA — valores no actualizados"
                    else "TELEMETRÍA OBSOLETA",
                    color = Color.Black,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.align(Alignment.BottomCenter).padding(10.dp)
                        .background(if (link.status == LinkStatus.LOST) SfColors.Danger else SfColors.Warn, RoundedCornerShape(6.dp))
                        .padding(horizontal = 12.dp, vertical = 6.dp),
                )
            }
        }

        // --- Telemetry panel ---------------------------------------------
        Panel(Modifier.width(270.dp).fillMaxHeight()) {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                val stale = link.status != LinkStatus.CONNECTED
                val valueColor = if (stale) SfColors.Warn else SfColors.Text
                SectionTitle("VUELO")
                TelemetryRow("Altitud rel.", fmt(telemetry.relativeAltM, 1, " m"), valueColor)
                TelemetryRow("Altitud MSL", fmt(telemetry.altMslM, 1, " m"), valueColor)
                TelemetryRow("Vel. suelo", fmt(telemetry.groundspeedMps, 1, " m/s"), valueColor)
                TelemetryRow("Vel. vertical", fmt(telemetry.climbMps, 1, " m/s"), valueColor)
                TelemetryRow("Rumbo", fmt(telemetry.headingDeg, 0, "°"), valueColor)
                SectionTitle("BATERÍA")
                TelemetryRow("Tensión", fmt(telemetry.batteryVoltageV, 2, " V"), valueColor)
                TelemetryRow("Corriente", fmt(telemetry.batteryCurrentA, 1, " A"), valueColor)
                TelemetryRow("Restante", telemetry.batteryRemainingPct?.let { "$it %" } ?: UNKNOWN, valueColor)
                SectionTitle("GPS")
                TelemetryRow("Fix", TelemetryReducer.fixLabel(telemetry.gpsFixType) ?: UNKNOWN, valueColor)
                TelemetryRow("Satélites", telemetry.satellitesVisible?.toString() ?: UNKNOWN, valueColor)
                TelemetryRow("HDOP", fmt(telemetry.hdop, 2), valueColor)
                TelemetryRow("Latitud", fmt(telemetry.latDeg, 6), valueColor)
                TelemetryRow("Longitud", fmt(telemetry.lonDeg, 6), valueColor)
                SectionTitle("MENSAJES DEL AUTOPILOTO")
                if (telemetry.messages.isEmpty()) Text(UNKNOWN, color = SfColors.Muted, fontSize = 12.sp)
                telemetry.messages.take(6).forEach {
                    Text(it.text, color = severityColor(it.severity), fontSize = 12.sp)
                }
                SectionTitle("CONTROLES (BLOQUEADOS)")
                ControlButtons(viewModel)
            }
        }
    }
}

@OptIn(UnstableApi::class)
@Composable
fun VideoSurface(video: VideoController, modifier: Modifier = Modifier.fillMaxSize()) {
    val player by video.playerFlow.collectAsStateWithLifecycle()
    androidx.compose.runtime.DisposableEffect(video) {
        video.onSurfaceAttached()
        onDispose { video.onSurfaceDetached() }
    }
    AndroidView(
        modifier = modifier,
        factory = { context ->
            PlayerView(context).apply {
                useController = false
                resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                setShutterBackgroundColor(android.graphics.Color.BLACK)
            }
        },
        update = { view -> view.player = player },
        onRelease = { view -> view.player = null },
    )
}

@Composable
private fun ControlButtons(viewModel: MainViewModel) {
    val commands = FlightCommand.entries
    commands.chunked(2).forEach { row ->
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            row.forEach { command ->
                OutlinedButton(
                    onClick = { viewModel.requestCommand(command) },
                    // Visually distinct, still tappable to explain why it is blocked.
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = SfColors.Locked),
                    modifier = Modifier.weight(1f).padding(vertical = 2.dp),
                ) {
                    Text("🔒 ${command.label}", fontSize = 11.sp, maxLines = 1)
                }
            }
            if (row.size == 1) Spacer(Modifier.weight(1f))
        }
    }
    Text(
        "Comandos de vuelo deshabilitados hasta completar validación SITL, análisis de seguridad y autorización. " +
            "El RC del mando sigue siendo el control del vehículo.",
        color = SfColors.Muted,
        fontSize = 10.sp,
        modifier = Modifier.padding(top = 4.dp),
    )
}
