package org.safeflight.android.mavlink;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

/**
 * Decodes a CRC-validated payload into a {@link MavlinkMessage}. Field offsets
 * follow the MAVLink wire order (fields sorted by size) and were verified
 * against pymavlink with the shared test vectors.
 */
public final class MavlinkDecoder {

    private MavlinkDecoder() {
    }

    /** Returns the decoded message, or {@code null} for unsupported message ids. */
    public static MavlinkMessage decode(MavlinkHeader header, byte[] rawPayload) {
        Integer fullLength = MavlinkIds.payloadLength(header.messageId);
        if (fullLength == null) {
            return null;
        }
        // MAVLink 2 truncates trailing zero bytes; restore them before decoding.
        byte[] p = rawPayload.length >= fullLength ? rawPayload : Arrays.copyOf(rawPayload, fullLength);
        ByteBuffer b = ByteBuffer.wrap(p).order(ByteOrder.LITTLE_ENDIAN);
        switch (header.messageId) {
            case MavlinkIds.HEARTBEAT:
                return new MavlinkMessage.Heartbeat(header,
                        b.getInt(0) & 0xFFFFFFFFL, u8(p, 4), u8(p, 5), u8(p, 6), u8(p, 7), u8(p, 8));
            case MavlinkIds.SYS_STATUS:
                return new MavlinkMessage.SysStatus(header,
                        u16(b, 14), b.getShort(16), p[30], u16(b, 18));
            case MavlinkIds.GPS_RAW_INT:
                return new MavlinkMessage.GpsRawInt(header,
                        u8(p, 28), u8(p, 29), u16(b, 20), b.getInt(8), b.getInt(12));
            case MavlinkIds.GLOBAL_POSITION_INT:
                return new MavlinkMessage.GlobalPositionInt(header,
                        b.getInt(4), b.getInt(8), b.getInt(12), b.getInt(16),
                        b.getShort(20), b.getShort(22), b.getShort(24), u16(b, 26));
            case MavlinkIds.VFR_HUD:
                return new MavlinkMessage.VfrHud(header,
                        b.getFloat(0), b.getFloat(4), b.getFloat(8), b.getFloat(12), b.getShort(16), u16(b, 18));
            case MavlinkIds.COMMAND_ACK:
                return new MavlinkMessage.CommandAck(header, u16(b, 0), u8(p, 2));
            case MavlinkIds.STATUSTEXT:
                return new MavlinkMessage.StatusText(header, u8(p, 0), decodeText(p, 1, 50));
            default:
                return null;
        }
    }

    private static int u8(byte[] bytes, int index) {
        return bytes[index] & 0xFF;
    }

    private static int u16(ByteBuffer b, int index) {
        return b.getShort(index) & 0xFFFF;
    }

    private static String decodeText(byte[] bytes, int offset, int maxLength) {
        int end = offset;
        while (end < offset + maxLength && bytes[end] != 0) {
            end++;
        }
        return new String(bytes, offset, end - offset, StandardCharsets.UTF_8);
    }
}
