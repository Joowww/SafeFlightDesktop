package org.safeflight.android.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.safeflight.android.state.LinkStatus
import org.safeflight.android.ui.theme.SfColors
import org.safeflight.android.video.VideoStatus
import java.util.Locale

const val UNKNOWN = "—"

fun fmt(value: Double?, decimals: Int, unit: String = ""): String =
    value?.let { String.format(Locale.US, "%.${decimals}f", it) + unit } ?: UNKNOWN

fun linkColor(status: LinkStatus): Color = when (status) {
    LinkStatus.CONNECTED -> SfColors.Ok
    LinkStatus.STALE, LinkStatus.WAITING_HEARTBEAT -> SfColors.Warn
    LinkStatus.LOST, LinkStatus.ERROR -> SfColors.Danger
    LinkStatus.DISCONNECTED -> SfColors.Muted
}

fun linkLabel(status: LinkStatus): String = when (status) {
    LinkStatus.DISCONNECTED -> "DESCONECTADO"
    LinkStatus.WAITING_HEARTBEAT -> "ESPERANDO HEARTBEAT"
    LinkStatus.CONNECTED -> "CONECTADO"
    LinkStatus.STALE -> "TELEMETRÍA OBSOLETA"
    LinkStatus.LOST -> "TELEMETRÍA PERDIDA"
    LinkStatus.ERROR -> "ERROR DE ENLACE"
}

fun videoColor(status: VideoStatus): Color = when (status) {
    VideoStatus.PLAYING -> SfColors.Ok
    VideoStatus.CONNECTING, VideoStatus.STALE -> SfColors.Warn
    VideoStatus.ERROR -> SfColors.Danger
    VideoStatus.IDLE -> SfColors.Muted
}

fun videoLabel(status: VideoStatus): String = when (status) {
    VideoStatus.IDLE -> "VÍDEO INACTIVO"
    VideoStatus.CONNECTING -> "VÍDEO CONECTANDO"
    VideoStatus.PLAYING -> "VÍDEO EN DIRECTO"
    VideoStatus.STALE -> "VÍDEO CONGELADO"
    VideoStatus.ERROR -> "VÍDEO SIN SEÑAL"
}

fun severityColor(severity: Int): Color = when {
    severity <= 3 -> SfColors.Danger
    severity == 4 -> SfColors.Warn
    else -> SfColors.Text
}

@Composable
fun StatusChip(label: String, color: Color, detail: String? = null) {
    Row(
        modifier = Modifier
            .background(Color(0xCC0E1116), RoundedCornerShape(6.dp))
            .border(1.dp, color, RoundedCornerShape(6.dp))
            .padding(horizontal = 8.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text("●", color = color, fontSize = 12.sp)
        Text(label, color = color, fontSize = 12.sp, fontWeight = FontWeight.Bold)
        if (detail != null) Text(detail, color = SfColors.Muted, fontSize = 11.sp, fontFamily = FontFamily.Monospace)
    }
}

@Composable
fun TelemetryRow(label: String, value: String, valueColor: Color = SfColors.Text) {
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = SfColors.Muted, fontSize = 13.sp)
        Text(
            value,
            color = if (value == UNKNOWN) SfColors.Muted else valueColor,
            fontSize = 15.sp,
            fontWeight = FontWeight.SemiBold,
            fontFamily = FontFamily.Monospace,
        )
    }
}

@Composable
fun SectionTitle(text: String) {
    Text(text, color = SfColors.Muted, fontSize = 11.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 8.dp, bottom = 2.dp))
}

@Composable
fun Panel(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Column(
        modifier
            .background(SfColors.Surface, RoundedCornerShape(10.dp))
            .border(1.dp, SfColors.Outline, RoundedCornerShape(10.dp))
            .padding(12.dp),
    ) { content() }
}
