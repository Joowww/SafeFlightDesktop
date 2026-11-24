package org.safeflight.android.mavlink;

import java.util.HashMap;
import java.util.Map;

/**
 * Message ids of the MAVLink subset decoded by SafeFlight Android, with the
 * CRC_EXTRA seed and the full (MAVLink 2) payload length of each one.
 * Only telemetry is decoded: there is deliberately no encoder for command
 * messages in this application.
 */
public final class MavlinkIds {
    public static final int HEARTBEAT = 0;
    public static final int SYS_STATUS = 1;
    public static final int GPS_RAW_INT = 24;
    public static final int GLOBAL_POSITION_INT = 33;
    public static final int VFR_HUD = 74;
    public static final int COMMAND_ACK = 77;
    public static final int STATUSTEXT = 253;

    private static final Map<Integer, Integer> CRC_EXTRA = new HashMap<>();
    private static final Map<Integer, Integer> PAYLOAD_LENGTH = new HashMap<>();

    static {
        register(HEARTBEAT, 50, 9);
        register(SYS_STATUS, 124, 31);
        register(GPS_RAW_INT, 24, 52);
        register(GLOBAL_POSITION_INT, 104, 28);
        register(VFR_HUD, 20, 20);
        register(COMMAND_ACK, 143, 10);
        register(STATUSTEXT, 83, 54);
    }

    private MavlinkIds() {
    }

    private static void register(int id, int crcExtra, int payloadLength) {
        CRC_EXTRA.put(id, crcExtra);
        PAYLOAD_LENGTH.put(id, payloadLength);
    }

    /** CRC_EXTRA of a supported message, or {@code null} when the id is not supported. */
    public static Integer crcExtra(int messageId) {
        return CRC_EXTRA.get(messageId);
    }

    /** Full payload length of a supported message, or {@code null}. */
    public static Integer payloadLength(int messageId) {
        return PAYLOAD_LENGTH.get(messageId);
    }
}
