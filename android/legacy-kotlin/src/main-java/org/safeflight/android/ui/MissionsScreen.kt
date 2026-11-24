package org.safeflight.android.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.safeflight.android.mission.ExecutionMode
import org.safeflight.android.mission.MissionSourceKind
import org.safeflight.android.mission.MissionStatus
import org.safeflight.android.ui.theme.SfColors

private fun statusColor(status: MissionStatus): Color = when (status) {
    MissionStatus.PENDING -> SfColors.Muted
    MissionStatus.APPROVED -> SfColors.Accent
    MissionStatus.RUNNING -> SfColors.Warn
    MissionStatus.COMPLETED -> SfColors.Ok
    MissionStatus.FAILED, MissionStatus.CANCELLED -> SfColors.Danger
}

@Composable
fun MissionsScreen(viewModel: MainViewModel) {
    val missions by viewModel.missions.collectAsStateWithLifecycle()
    Column(Modifier.fillMaxSize().padding(12.dp)) {
        if (viewModel.missionSource == MissionSourceKind.DEMO) {
            Text(
                "DATOS DE DEMOSTRACIÓN — no existe todavía conexión con el supervisor de misiones (Hermes). " +
                    "Ninguna misión mostrada es real.",
                color = Color.Black,
                fontWeight = FontWeight.Bold,
                fontSize = 13.sp,
                modifier = Modifier.fillMaxWidth().background(SfColors.Warn, RoundedCornerShape(6.dp)).padding(10.dp),
            )
        }
        LazyColumn(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            MissionStatus.entries.forEach { status ->
                val group = missions.filter { it.status == status }
                if (group.isNotEmpty()) {
                    item { SectionTitle(status.name) }
                    items(group, key = { it.id }) { mission ->
                        Panel(Modifier.fillMaxWidth()) {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("${mission.id} · ${mission.title}", fontWeight = FontWeight.Bold, color = SfColors.Text)
                                Text(mission.status.name, color = statusColor(mission.status), fontWeight = FontWeight.Bold)
                            }
                            Text(
                                "${mission.vehicle} · " + if (mission.executionMode == ExecutionMode.SIMULATED) "SIMULACIÓN" else "FÍSICA",
                                color = if (mission.executionMode == ExecutionMode.PHYSICAL) SfColors.Danger else SfColors.Muted,
                                fontSize = 12.sp,
                            )
                            Text(mission.summary, color = SfColors.Text, fontSize = 13.sp)
                            mission.result?.let { Text("Resultado: $it", color = SfColors.Ok, fontSize = 12.sp) }
                            mission.error?.let { Text("Fallo: $it", color = SfColors.Danger, fontSize = 12.sp) }
                        }
                    }
                }
            }
        }
    }
}
