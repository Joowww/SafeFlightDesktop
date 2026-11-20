package org.safeflight.android.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.safeflight.android.config.ConnectionProfile
import org.safeflight.android.diagnostics.LogLevel
import org.safeflight.android.state.LinkStatus
import org.safeflight.android.ui.theme.SfColors
import org.safeflight.android.video.VideoController
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Editable text copy of a profile; converted back with [toProfile]. */
private data class ProfileForm(
    val id: String, val name: String, val kind: String, val builtin: Boolean, val notes: String,
    val transport: String, val localHost: String, val localPort: String,
    val remoteHost: String, val remotePort: String, val gcsHeartbeat: Boolean,
    val videoMode: String, val rtspUrl: String, val rtspTransport: String,
    val staleS: String, val videoStaleS: String, val videoRetryS: String, val verbose: Boolean,
    val base: ConnectionProfile,
) {
    fun toProfile(): ConnectionProfile? {
        val lp = localPort.toIntOrNull() ?: return null
        val rp = remotePort.toIntOrNull() ?: return null
        val st = staleS.toDoubleOrNull() ?: return null
        val vs = videoStaleS.toDoubleOrNull() ?: return null
        val vr = videoRetryS.toDoubleOrNull() ?: return null
        return base.copy(
            id = id, name = name.trim(), kind = kind, notes = notes,
            mavlink = base.mavlink.copy(
                transport = transport, localHost = localHost.trim(), localPort = lp,
                remoteHost = remoteHost.trim(), remotePort = rp, sendGcsHeartbeat = gcsHeartbeat,
            ),
            video = base.video.copy(mode = videoMode, rtspUrl = rtspUrl.trim(), rtspTransport = rtspTransport),
            timeouts = base.timeouts.copy(telemetryStaleS = st, videoStaleS = vs, videoReconnectIntervalS = vr),
            diagnostics = base.diagnostics.copy(verboseLogging = verbose),
        )
    }

    companion object {
        fun from(p: ConnectionProfile) = ProfileForm(
            p.id, p.name, p.kind, p.builtin, p.notes,
            p.mavlink.transport, p.mavlink.localHost, p.mavlink.localPort.toString(),
            p.mavlink.remoteHost, p.mavlink.remotePort.toString(), p.mavlink.sendGcsHeartbeat,
            p.video.mode, p.video.rtspUrl, p.video.rtspTransport,
            p.timeouts.telemetryStaleS.toString(), p.timeouts.videoStaleS.toString(),
            p.timeouts.videoReconnectIntervalS.toString(), p.diagnostics.verboseLogging, p,
        )
    }
}

@Composable
fun ConnectionScreen(
    viewModel: MainViewModel,
    video: VideoController,
    onRestartVideo: () -> Unit,
    onStopVideo: () -> Unit,
) {
    val doc by viewModel.profiles.collectAsStateWithLifecycle()
    val link by viewModel.link.collectAsStateWithLifecycle()
    val counters by viewModel.counters.collectAsStateWithLifecycle()
    val videoState by video.state.collectAsStateWithLifecycle()
    val logs by viewModel.logEntries.collectAsStateWithLifecycle()
    val active = doc.profiles.firstOrNull { it.id == doc.activeProfileId } ?: doc.profiles.firstOrNull() ?: return

    var form by remember(active) { mutableStateOf(ProfileForm.from(active)) }
    var errors by remember(active) { mutableStateOf<List<String>>(emptyList()) }

    Row(Modifier.fillMaxSize().padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        // --- Profile editor ----------------------------------------------------
        Panel(Modifier.weight(1.1f).fillMaxHeight()) {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                SectionTitle("PERFIL ACTIVO")
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    doc.profiles.forEach { p ->
                        FilterChip(selected = p.id == doc.activeProfileId, onClick = {
                            viewModel.selectProfile(p.id); if (videoState.status != org.safeflight.android.video.VideoStatus.IDLE) onRestartVideo()
                        }, label = { Text(p.name) })
                    }
                }
                if (form.notes.isNotBlank()) Text(form.notes, color = SfColors.Warn, fontSize = 12.sp)
                Field("Nombre", form.name, Modifier.fillMaxWidth()) { form = form.copy(name = it) }
                SectionTitle("TELEMETRÍA MAVLINK")
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(form.transport == "udp_listen", { form = form.copy(transport = "udp_listen") }, { Text("UDP escucha") })
                    FilterChip(form.transport == "udp_connect", { form = form.copy(transport = "udp_connect", gcsHeartbeat = true) }, { Text("UDP hacia remoto") })
                }
                if (form.transport == "udp_listen") {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Field("Dirección local", form.localHost, Modifier.weight(1f)) { form = form.copy(localHost = it) }
                        Field("Puerto local", form.localPort, Modifier.width(120.dp), numeric = true) { form = form.copy(localPort = it) }
                    }
                } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Field("IP remota", form.remoteHost, Modifier.weight(1f)) { form = form.copy(remoteHost = it) }
                        Field("Puerto remoto", form.remotePort, Modifier.width(120.dp), numeric = true) { form = form.copy(remotePort = it) }
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Switch(form.gcsHeartbeat, { form = form.copy(gcsHeartbeat = it) })
                    Text(
                        "  Enviar heartbeat de GCS (1 Hz). Si FS_GCS_ENABLE está activo en ArduPilot, " +
                            "dejar de enviarlo puede activar el failsafe de GCS.",
                        color = SfColors.Muted, fontSize = 11.sp,
                    )
                }
                SectionTitle("VÍDEO")
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(form.videoMode == "rtsp", { form = form.copy(videoMode = "rtsp") }, { Text("RTSP") })
                    FilterChip(form.videoMode == "none", { form = form.copy(videoMode = "none") }, { Text("Sin vídeo") })
                    FilterChip(form.rtspTransport == "tcp", { form = form.copy(rtspTransport = "tcp") }, { Text("TCP") })
                    FilterChip(form.rtspTransport == "udp", { form = form.copy(rtspTransport = "udp") }, { Text("UDP") })
                }
                Field("URL RTSP", form.rtspUrl, Modifier.fillMaxWidth()) { form = form.copy(rtspUrl = it) }
                SectionTitle("SUPERVISIÓN")
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Field("Telemetría obsoleta (s)", form.staleS, Modifier.weight(1f), numeric = true) { form = form.copy(staleS = it) }
                    Field("Vídeo obsoleto (s)", form.videoStaleS, Modifier.weight(1f), numeric = true) { form = form.copy(videoStaleS = it) }
                    Field("Reintento vídeo (s)", form.videoRetryS, Modifier.weight(1f), numeric = true) { form = form.copy(videoRetryS = it) }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Switch(form.verbose, { form = form.copy(verbose = it) })
                    Text("  Registro detallado", color = SfColors.Muted, fontSize = 12.sp)
                }
                errors.forEach { Text("• $it", color = SfColors.Danger, fontSize = 12.sp) }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Button(onClick = {
                        val profile = form.toProfile()
                        errors = if (profile == null) listOf("Revisa los campos numéricos") else viewModel.saveProfile(profile)
                        if (errors.isEmpty()) onRestartVideo()
                    }) { Text("Guardar") }
                    OutlinedButton(onClick = { viewModel.duplicateProfile(active.id) }) { Text("Duplicar") }
                    if (active.builtin) {
                        TextButton(onClick = { viewModel.restoreProfile(active.id); onRestartVideo() }) { Text("Restaurar fábrica") }
                    } else {
                        TextButton(onClick = { viewModel.deleteProfile(active.id)?.let { errors = listOf(it) } }) { Text("Eliminar") }
                    }
                }
            }
        }

        // --- Diagnostics ---------------------------------------------------------
        Panel(Modifier.weight(1f).fillMaxHeight()) {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                SectionTitle("TELEMETRÍA")
                StatusChip(linkLabel(link.status), linkColor(link.status))
                TelemetryRow("Endpoint", link.endpoint.ifBlank { UNKNOWN })
                TelemetryRow("Último heartbeat", link.heartbeatAgeMs?.let { fmt(it / 1000.0, 1, " s") } ?: UNKNOWN)
                TelemetryRow("Datagramas", counters.datagrams.toString())
                TelemetryRow("Tramas válidas / descartadas", "${counters.framesAccepted} / ${counters.framesRejected}")
                TelemetryRow("Heartbeats GCS enviados", counters.gcsHeartbeatsSent.toString())
                TelemetryRow("Reintentos socket", link.reconnectAttempts.toString())
                link.lastError?.let { Text(it, color = SfColors.Danger, fontSize = 11.sp) }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Button(
                        onClick = viewModel::connectTelemetry,
                        colors = ButtonDefaults.buttonColors(containerColor = SfColors.Ok.copy(alpha = 0.8f)),
                    ) { Text("Conectar") }
                    OutlinedButton(onClick = viewModel::disconnectTelemetry, enabled = link.status != LinkStatus.DISCONNECTED) {
                        Text("Desconectar")
                    }
                }
                SectionTitle("VÍDEO")
                StatusChip(videoLabel(videoState.status), videoColor(videoState.status))
                androidx.compose.foundation.layout.Box(
                    Modifier.fillMaxWidth().height(150.dp)
                        .background(androidx.compose.ui.graphics.Color.Black),
                ) { VideoSurface(video, Modifier.fillMaxSize()) }
                TelemetryRow("URL", videoState.url.ifBlank { UNKNOWN })
                TelemetryRow("Resolución", if (videoState.width != null) "${videoState.width}x${videoState.height}" else UNKNOWN)
                TelemetryRow("Edad último fotograma", videoState.lastFrameAgeMs?.let { "$it ms" } ?: UNKNOWN)
                TelemetryRow("Fotogramas", videoState.framesRendered.toString())
                TelemetryRow("Reintentos", videoState.retries.toString())
                videoState.lastError?.let { Text(it, color = SfColors.Danger, fontSize = 11.sp) }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Button(onClick = onRestartVideo) { Text("Reiniciar vídeo") }
                    OutlinedButton(onClick = onStopVideo) { Text("Detener vídeo") }
                }
                SectionTitle("REGISTRO")
                val formatter = remember { SimpleDateFormat("HH:mm:ss", Locale.US) }
                logs.take(40).forEach { entry ->
                    Text(
                        "${formatter.format(Date(entry.atMs))} ${entry.source}: ${entry.message}",
                        color = when (entry.level) {
                            LogLevel.ERROR -> SfColors.Danger
                            LogLevel.WARN -> SfColors.Warn
                            else -> SfColors.Muted
                        },
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
        }
    }
}

@Composable
private fun Field(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    numeric: Boolean = false,
    onChange: (String) -> Unit,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label, fontSize = 12.sp) },
        singleLine = true,
        keyboardOptions = if (numeric) KeyboardOptions(keyboardType = KeyboardType.Decimal) else KeyboardOptions.Default,
        modifier = modifier,
    )
}
