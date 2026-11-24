package org.safeflight.android.state

import org.safeflight.android.mavlink.ArduCopterModes
import org.safeflight.android.mavlink.MavConstants
import org.safeflight.android.mavlink.MavlinkMessage

/**
 * Vehicle telemetry as shown to the operator. Every field is nullable:
 * `null` means "unknown" and is rendered as such. Values are never invented
 * and sentinel values defined by MAVLink (e.g. UINT16_MAX) map to `null`.
 * Conversions follow shared/protocols/mavlink-telemetry-contract.md.
 */
data class TelemetryState(
    val vehicleSystemId: Int? = null,
    val vehicleComponentId: Int? = null,
    val vehicleType: Int? = null,
    val autopilot: Int? = null,
    val armed: Boolean? = null,
    val customMode: Long? = null,
    val flightMode: String? = null,
    val systemStatus: Int? = null,
    val batteryVoltageV: Double? = null,
    val batteryCurrentA: Double? = null,
    val batteryRemainingPct: Int? = null,
    val latDeg: Double? = null,
    val lonDeg: Double? = null,
    val altMslM: Double? = null,
    val relativeAltM: Double? = null,
    val headingDeg: Double? = null,
    val groundspeedMps: Double? = null,
    val airspeedMps: Double? = null,
    val climbMps: Double? = null,
    val gpsFixType: Int? = null,
    val satellitesVisible: Int? = null,
    val hdop: Double? = null,
    val lastHeartbeatAtMs: Long? = null,
    val messages: List<StatusMessage> = emptyList(),
    val lastCommandAck: CommandAckInfo? = null,
)

data class StatusMessage(val severity: Int, val text: String, val receivedAtMs: Long)

data class CommandAckInfo(val command: Int, val result: Int, val receivedAtMs: Long)

object TelemetryReducer {
    const val MAX_MESSAGES = 30
    private const val UINT16_MAX = 65535

    /**
     * Applies [message] to [state]. The first vehicle heartbeat selects the
     * vehicle system id; messages from other systems (GCS, other vehicles)
     * are ignored so they cannot overwrite the vehicle state.
     */
    fun reduce(state: TelemetryState, message: MavlinkMessage, nowMs: Long): TelemetryState {
        val sysId = message.header.systemId
        if (message is MavlinkMessage.Heartbeat) {
            if (!message.isVehicle) return state
            val compId = message.header.componentId
            if (state.vehicleSystemId != null &&
                (state.vehicleSystemId != sysId || state.vehicleComponentId != compId)
            ) {
                return state
            }
            val mode = if (message.autopilot == MavConstants.MAV_AUTOPILOT_ARDUPILOTMEGA) {
                ArduCopterModes.name(message.customMode)
            } else {
                "UNKNOWN(${message.customMode})"
            }
            return state.copy(
                vehicleSystemId = sysId,
                vehicleComponentId = compId,
                vehicleType = message.type,
                autopilot = message.autopilot,
                armed = message.armed,
                customMode = message.customMode,
                flightMode = mode,
                systemStatus = message.systemStatus,
                lastHeartbeatAtMs = nowMs,
            )
        }
        if (state.vehicleSystemId == null || sysId != state.vehicleSystemId) return state

        return when (message) {
            is MavlinkMessage.SysStatus -> state.copy(
                batteryVoltageV = if (message.voltageBatteryMv == UINT16_MAX) null else message.voltageBatteryMv / 1000.0,
                batteryCurrentA = if (message.currentBatteryCa == -1) null else message.currentBatteryCa / 100.0,
                batteryRemainingPct = if (message.batteryRemaining == -1) null else message.batteryRemaining,
            )
            is MavlinkMessage.GlobalPositionInt -> {
                val noFix = message.latE7 == 0 && message.lonE7 == 0
                state.copy(
                    latDeg = if (noFix) null else message.latE7 / 1e7,
                    lonDeg = if (noFix) null else message.lonE7 / 1e7,
                    altMslM = message.altMm / 1000.0,
                    relativeAltM = message.relativeAltMm / 1000.0,
                    headingDeg = if (message.hdgCdeg == UINT16_MAX) null else message.hdgCdeg / 100.0,
                )
            }
            is MavlinkMessage.VfrHud -> state.copy(
                groundspeedMps = message.groundspeed.toDouble().takeIf { it.isFinite() },
                airspeedMps = message.airspeed.toDouble().takeIf { it.isFinite() },
                climbMps = message.climb.toDouble().takeIf { it.isFinite() },
            )
            is MavlinkMessage.GpsRawInt -> state.copy(
                gpsFixType = message.fixType,
                satellitesVisible = if (message.satellitesVisible == 255) null else message.satellitesVisible,
                hdop = if (message.eph == UINT16_MAX) null else message.eph / 100.0,
            )
            is MavlinkMessage.StatusText -> state.copy(
                messages = (listOf(StatusMessage(message.severity, message.text, nowMs)) + state.messages)
                    .take(MAX_MESSAGES),
            )
            is MavlinkMessage.CommandAck -> state.copy(
                lastCommandAck = CommandAckInfo(message.command, message.result, nowMs),
            )
            is MavlinkMessage.Heartbeat -> state
        }
    }

    /** Human-readable GPS fix label; null when unknown. */
    fun fixLabel(fixType: Int?): String? = when (fixType) {
        null -> null
        0, 1 -> "SIN FIX"
        2 -> "2D"
        3 -> "3D"
        4 -> "DGPS"
        5 -> "RTK FLOAT"
        6 -> "RTK FIX"
        else -> "TIPO $fixType"
    }
}
