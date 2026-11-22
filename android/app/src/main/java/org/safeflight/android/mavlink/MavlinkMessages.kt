package org.safeflight.android.mavlink

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Subset of the MAVLink common/ardupilotmega dialect decoded by SafeFlight
 * Android. Field offsets follow the MAVLink wire order (fields sorted by size)
 * and were verified against pymavlink. Only telemetry is decoded: there is
 * deliberately no encoder for command messages in this application.
 */
object MavlinkIds {
    const val HEARTBEAT = 0
    const val SYS_STATUS = 1
    const val GPS_RAW_INT = 24
    const val GLOBAL_POSITION_INT = 33
    const val VFR_HUD = 74
    const val COMMAND_ACK = 77
    const val STATUSTEXT = 253

    /** CRC_EXTRA seeds and full (v2) payload lengths of the supported messages. */
    val CRC_EXTRA: Map<Int, Int> = mapOf(
        HEARTBEAT to 50,
        SYS_STATUS to 124,
        GPS_RAW_INT to 24,
        GLOBAL_POSITION_INT to 104,
        VFR_HUD to 20,
        COMMAND_ACK to 143,
        STATUSTEXT to 83,
    )
    val PAYLOAD_LENGTH: Map<Int, Int> = mapOf(
        HEARTBEAT to 9,
        SYS_STATUS to 31,
        GPS_RAW_INT to 52,
        GLOBAL_POSITION_INT to 28,
        VFR_HUD to 20,
        COMMAND_ACK to 10,
        STATUSTEXT to 54,
    )
}

/** MAV_TYPE / MAV_AUTOPILOT values needed to classify heartbeats. */
object MavConstants {
    const val MAV_TYPE_GCS = 6
    const val MAV_TYPE_ONBOARD_CONTROLLER = 18
    const val MAV_AUTOPILOT_ARDUPILOTMEGA = 3
    const val MAV_AUTOPILOT_INVALID = 8
    const val MAV_MODE_FLAG_SAFETY_ARMED = 0x80
    const val MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 0x01
    const val MAV_STATE_ACTIVE = 4
}

sealed interface MavlinkMessage {
    val header: MavlinkHeader

    data class Heartbeat(
        override val header: MavlinkHeader,
        val customMode: Long,
        val type: Int,
        val autopilot: Int,
        val baseMode: Int,
        val systemStatus: Int,
        val mavlinkVersion: Int,
    ) : MavlinkMessage {
        val armed: Boolean get() = (baseMode and MavConstants.MAV_MODE_FLAG_SAFETY_ARMED) != 0
        val isVehicle: Boolean
            get() = autopilot != MavConstants.MAV_AUTOPILOT_INVALID &&
                type != MavConstants.MAV_TYPE_GCS && type != MavConstants.MAV_TYPE_ONBOARD_CONTROLLER
    }

    data class SysStatus(
        override val header: MavlinkHeader,
        val voltageBatteryMv: Int,
        val currentBatteryCa: Int,
        val batteryRemaining: Int,
        val dropRateComm: Int,
    ) : MavlinkMessage

    data class GpsRawInt(
        override val header: MavlinkHeader,
        val fixType: Int,
        val satellitesVisible: Int,
        val eph: Int,
        val latE7: Int,
        val lonE7: Int,
    ) : MavlinkMessage

    data class GlobalPositionInt(
        override val header: MavlinkHeader,
        val latE7: Int,
        val lonE7: Int,
        val altMm: Int,
        val relativeAltMm: Int,
        val vxCms: Int,
        val vyCms: Int,
        val vzCms: Int,
        val hdgCdeg: Int,
    ) : MavlinkMessage

    data class VfrHud(
        override val header: MavlinkHeader,
        val airspeed: Float,
        val groundspeed: Float,
        val alt: Float,
        val climb: Float,
        val heading: Int,
        val throttle: Int,
    ) : MavlinkMessage

    data class CommandAck(
        override val header: MavlinkHeader,
        val command: Int,
        val result: Int,
    ) : MavlinkMessage

    data class StatusText(
        override val header: MavlinkHeader,
        val severity: Int,
        val text: String,
    ) : MavlinkMessage
}

data class MavlinkHeader(
    val version: Int,
    val sequence: Int,
    val systemId: Int,
    val componentId: Int,
    val messageId: Int,
)

/** Decodes a CRC-validated payload. Returns null for unsupported ids. */
object MavlinkDecoder {
    fun decode(header: MavlinkHeader, rawPayload: ByteArray): MavlinkMessage? {
        val fullLength = MavlinkIds.PAYLOAD_LENGTH[header.messageId] ?: return null
        // MAVLink 2 truncates trailing zero bytes; restore them before decoding.
        val payload = if (rawPayload.size >= fullLength) rawPayload else rawPayload.copyOf(fullLength)
        val b = ByteBuffer.wrap(payload).order(ByteOrder.LITTLE_ENDIAN)
        return when (header.messageId) {
            MavlinkIds.HEARTBEAT -> MavlinkMessage.Heartbeat(
                header = header,
                customMode = b.getInt(0).toLong() and 0xFFFFFFFFL,
                type = u8(payload, 4),
                autopilot = u8(payload, 5),
                baseMode = u8(payload, 6),
                systemStatus = u8(payload, 7),
                mavlinkVersion = u8(payload, 8),
            )
            MavlinkIds.SYS_STATUS -> MavlinkMessage.SysStatus(
                header = header,
                voltageBatteryMv = u16(b, 14),
                currentBatteryCa = b.getShort(16).toInt(),
                batteryRemaining = payload[30].toInt(),
                dropRateComm = u16(b, 18),
            )
            MavlinkIds.GPS_RAW_INT -> MavlinkMessage.GpsRawInt(
                header = header,
                latE7 = b.getInt(8),
                lonE7 = b.getInt(12),
                eph = u16(b, 20),
                fixType = u8(payload, 28),
                satellitesVisible = u8(payload, 29),
            )
            MavlinkIds.GLOBAL_POSITION_INT -> MavlinkMessage.GlobalPositionInt(
                header = header,
                latE7 = b.getInt(4),
                lonE7 = b.getInt(8),
                altMm = b.getInt(12),
                relativeAltMm = b.getInt(16),
                vxCms = b.getShort(20).toInt(),
                vyCms = b.getShort(22).toInt(),
                vzCms = b.getShort(24).toInt(),
                hdgCdeg = u16(b, 26),
            )
            MavlinkIds.VFR_HUD -> MavlinkMessage.VfrHud(
                header = header,
                airspeed = b.getFloat(0),
                groundspeed = b.getFloat(4),
                alt = b.getFloat(8),
                climb = b.getFloat(12),
                heading = b.getShort(16).toInt(),
                throttle = u16(b, 18),
            )
            MavlinkIds.COMMAND_ACK -> MavlinkMessage.CommandAck(
                header = header,
                command = u16(b, 0),
                result = u8(payload, 2),
            )
            MavlinkIds.STATUSTEXT -> MavlinkMessage.StatusText(
                header = header,
                severity = u8(payload, 0),
                text = decodeText(payload, 1, 50),
            )
            else -> null
        }
    }

    private fun u8(bytes: ByteArray, index: Int): Int = bytes[index].toInt() and 0xFF
    private fun u16(b: ByteBuffer, index: Int): Int = b.getShort(index).toInt() and 0xFFFF

    private fun decodeText(bytes: ByteArray, offset: Int, maxLength: Int): String {
        var end = offset
        while (end < offset + maxLength && bytes[end].toInt() != 0) end++
        return String(bytes, offset, end - offset, Charsets.UTF_8)
    }
}
