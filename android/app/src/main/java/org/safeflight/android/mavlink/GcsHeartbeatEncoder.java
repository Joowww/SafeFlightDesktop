package org.safeflight.android.mavlink;

/**
 * The only MAVLink encoder in SafeFlight Android: a ground-station HEARTBEAT
 * (MAV_TYPE_GCS, MAV_AUTOPILOT_INVALID). It announces the station so that a
 * router (e.g. MAVProxy) learns its UDP address. It carries no command.
 *
 * <p>Note for operators: if ArduPilot's GCS failsafe (FS_GCS_ENABLE) is active,
 * stopping these heartbeats can trigger that failsafe. Sending them is
 * therefore an explicit per-profile option, disabled by default.
 */
public final class GcsHeartbeatEncoder {
    private final int systemId;
    private final int componentId;
    private int sequence = 0;

    public GcsHeartbeatEncoder() {
        this(255, 190);
    }

    public GcsHeartbeatEncoder(int systemId, int componentId) {
        this.systemId = systemId;
        this.componentId = componentId;
    }

    /** Returns one complete MAVLink 2 HEARTBEAT frame. */
    public byte[] encode() {
        byte[] payload = {
            0, 0, 0, 0,                                    // custom_mode
            (byte) MavConstants.MAV_TYPE_GCS,
            (byte) MavConstants.MAV_AUTOPILOT_INVALID,
            0,                                             // base_mode
            0,                                             // system_status
            3,                                             // mavlink_version
        };
        byte[] frame = new byte[10 + payload.length + 2];
        frame[0] = (byte) MavlinkParser.STX_V2;
        frame[1] = (byte) payload.length;
        frame[2] = 0;                                      // incompat_flags
        frame[3] = 0;                                      // compat_flags
        frame[4] = (byte) (sequence & 0xFF);
        frame[5] = (byte) systemId;
        frame[6] = (byte) componentId;
        frame[7] = (byte) MavlinkIds.HEARTBEAT;            // message id (3 bytes)
        frame[8] = 0;
        frame[9] = 0;
        System.arraycopy(payload, 0, frame, 10, payload.length);
        int crc = MavlinkCrc.compute(frame, 1, 9 + payload.length);
        crc = MavlinkCrc.accumulate(MavlinkIds.crcExtra(MavlinkIds.HEARTBEAT), crc);
        frame[10 + payload.length] = (byte) (crc & 0xFF);
        frame[11 + payload.length] = (byte) ((crc >>> 8) & 0xFF);
        sequence = (sequence + 1) & 0xFF;
        return frame;
    }
}
