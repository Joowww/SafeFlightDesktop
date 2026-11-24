package org.safeflight.android.mavlink;

/** CRC-16/MCRF4XX ("X.25") as defined by the MAVLink specification. */
public final class MavlinkCrc {
    public static final int INITIAL = 0xFFFF;

    private MavlinkCrc() {
    }

    /** Adds one byte to the running checksum. */
    public static int accumulate(int b, int crc) {
        int tmp = (b & 0xFF) ^ (crc & 0xFF);
        tmp = (tmp ^ (tmp << 4)) & 0xFF;
        return ((crc >>> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >>> 4)) & 0xFFFF;
    }

    public static int compute(byte[] bytes, int offset, int length) {
        return compute(bytes, offset, length, INITIAL);
    }

    public static int compute(byte[] bytes, int offset, int length, int crc) {
        int value = crc;
        for (int i = offset; i < offset + length; i++) {
            value = accumulate(bytes[i], value);
        }
        return value;
    }
}
