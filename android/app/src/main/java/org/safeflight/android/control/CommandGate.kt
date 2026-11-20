package org.safeflight.android.control

import org.safeflight.android.state.LinkState
import org.safeflight.android.state.LinkStatus
import org.safeflight.android.state.TelemetryState

/** Flight operations prepared in the UI. None of them is executable yet. */
enum class FlightCommand(val label: String) {
    ARM("ARM"),
    DISARM("DISARM"),
    TAKEOFF("TAKEOFF"),
    LAND("LAND"),
    SET_MODE("MODO"),
    START_MISSION("INICIAR MISIÓN"),
    ABORT_MISSION("DETENER MISIÓN"),
}

sealed interface CommandDecision {
    data class Blocked(val reasons: List<String>) : CommandDecision
    /** Not produced while [CommandGate.PHYSICAL_COMMANDS_ENABLED] is false. */
    data object Allowed : CommandDecision
}

/**
 * Single decision point for every future vehicle command.
 *
 * Physical commands are disabled at compile time. The pre-conditions are
 * still evaluated so that the operator sees why a command would be refused,
 * and so that the future implementation keeps one audited entry point
 * (authorisation, confirmation, vehicle state, ACK with timeout, no
 * duplicate commands). The MAVLink layer contains no command encoder.
 */
object CommandGate {
    const val PHYSICAL_COMMANDS_ENABLED = false

    const val DISABLED_REASON =
        "Controles deshabilitados: pendientes de pruebas SITL, análisis de seguridad y autorización operativa"

    fun evaluate(command: FlightCommand, telemetry: TelemetryState, link: LinkState): CommandDecision {
        val reasons = mutableListOf<String>()
        if (!PHYSICAL_COMMANDS_ENABLED) reasons += DISABLED_REASON
        if (link.status != LinkStatus.CONNECTED) reasons += "Sin telemetría MAVLink vigente"
        if (telemetry.vehicleSystemId == null) reasons += "Vehículo no identificado"
        when (command) {
            FlightCommand.ARM, FlightCommand.TAKEOFF ->
                if (telemetry.armed == true && command == FlightCommand.ARM) reasons += "El vehículo ya está armado"
            FlightCommand.DISARM, FlightCommand.LAND ->
                if (telemetry.armed == false) reasons += "El vehículo no está armado"
            else -> Unit
        }
        return if (reasons.isEmpty() && PHYSICAL_COMMANDS_ENABLED) CommandDecision.Allowed else CommandDecision.Blocked(reasons)
    }
}
