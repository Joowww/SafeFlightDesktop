package org.safeflight.android.mission

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Lifecycle of a mission as reported by the mission supervisor. */
enum class MissionStatus { PENDING, APPROVED, RUNNING, COMPLETED, FAILED, CANCELLED }

/** Whether a mission runs in simulation (SITL/Gazebo) or on a physical vehicle. */
enum class ExecutionMode { SIMULATED, PHYSICAL }

data class Mission(
    val id: String,
    val title: String,
    val vehicle: String,
    val status: MissionStatus,
    val executionMode: ExecutionMode,
    val summary: String,
    val result: String? = null,
    val error: String? = null,
    val updatedAt: String,
)

enum class MissionSourceKind { DEMO, SUPERVISOR }

/**
 * Read-only view of missions. The planned implementation will be a client of
 * the multi-agent supervisor (Hermes/LangGraph); see
 * docs/architecture/integration-points.md. No such client exists yet.
 */
interface MissionRepository {
    val source: MissionSourceKind
    val missions: StateFlow<List<Mission>>
}

/** Clearly labelled sample data so that the screen can be developed and reviewed. */
class DemoMissionRepository : MissionRepository {
    override val source = MissionSourceKind.DEMO
    private val _missions = MutableStateFlow(
        listOf(
            Mission("DEMO-001", "Inspección perímetro norte", "Dron", MissionStatus.PENDING,
                ExecutionMode.SIMULATED, "Pendiente de aprobación del operador", updatedAt = "—"),
            Mission("DEMO-002", "Reconocimiento de ruta", "Rover", MissionStatus.APPROVED,
                ExecutionMode.SIMULATED, "Aprobada, a la espera de ejecución", updatedAt = "—"),
            Mission("DEMO-003", "Búsqueda coordinada", "Dron + Rover", MissionStatus.RUNNING,
                ExecutionMode.SIMULATED, "Fase 2 de 4 (simulación Gazebo)", updatedAt = "—"),
            Mission("DEMO-004", "Mapeo de zona A", "Dron", MissionStatus.COMPLETED,
                ExecutionMode.SIMULATED, "Completada", result = "12 waypoints cubiertos", updatedAt = "—"),
            Mission("DEMO-005", "Entrega de muestra", "Rover", MissionStatus.FAILED,
                ExecutionMode.SIMULATED, "Abortada por el supervisor", error = "Obstáculo no evitable", updatedAt = "—"),
        ),
    )
    override val missions: StateFlow<List<Mission>> = _missions.asStateFlow()
}
