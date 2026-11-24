package org.safeflight.android.mavlink

/**
 * The only MAVLink encoder in SafeFlight Android: a ground-station HEARTBEAT
 * (MAV_TYPE_GCS, MAV_AUTOPILOT_INVALID). It announces the station so that a
 * router (e.g. MAVProxy) learns its UDP address. It carries no command.
 *
 * Note for operators: if ArduPilot's GCS failsafe (FS_GCS_ENABLE) is active,
 * stopping these heartbeats can trigger that failsafe. Sending them is
 * therefore an explicit per-profile option, disabled by default.
 */
class GcsHeartbeatEncoder(
    private val systemId: Int = 255,
    private val componentId: Int = 190,
) {
    private var sequence = 0

    fun encode(): ByteArray {
        val payload = byteArrayOf(
            0, 0, 0, 0, // custom_mode
            MavConstants.MAV_TYPE_GCS.toByte(),
            MavConstants.MAV_AUTOPILOT_INVALID.toByte(),
            0, // base_mode
            0, // system_status
            3, // mavlink_version
        )
        val frame = ByteArray(10 + payload.size + 2)
        frame[0] = MavlinkParser.STX_V2.toByte()
        frame[1] = payload.size.toByte()
        frame[2] = 0
        frame[3] = 0
        frame[4] = (sequence and 0xFF).toByte()
        frame[5] = systemId.toByte()
        frame[6] = componentId.toByte()
        frame[7] = MavlinkIds.HEARTBEAT.toByte()
        frame[8] = 0
        frame[9] = 0
        System.arraycopy(payload, 0, frame, 10, payload.size)
        var crc = MavlinkCrc.compute(frame, 1, 9 + payload.size)
        crc = MavlinkCrc.accumulate(MavlinkIds.CRC_EXTRA.getValue(MavlinkIds.HEARTBEAT), crc)
        frame[10 + payload.size] = (crc and 0xFF).toByte()
        frame[11 + payload.size] = (crc ushr 8 and 0xFF).toByte()
        sequence = (sequence + 1) and 0xFF
        return frame
    }
}
