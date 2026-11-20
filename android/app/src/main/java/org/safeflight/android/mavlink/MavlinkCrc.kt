package org.safeflight.android.mavlink

/** CRC-16/MCRF4XX ("X.25") as defined by the MAVLink specification. */
object MavlinkCrc {
    const val INITIAL: Int = 0xFFFF

    fun accumulate(byte: Int, crc: Int): Int {
        var tmp = (byte and 0xFF) xor (crc and 0xFF)
        tmp = (tmp xor (tmp shl 4)) and 0xFF
        return ((crc ushr 8) xor (tmp shl 8) xor (tmp shl 3) xor (tmp ushr 4)) and 0xFFFF
    }

    fun compute(bytes: ByteArray, offset: Int, length: Int, crc: Int = INITIAL): Int {
        var value = crc
        for (i in offset until offset + length) {
            value = accumulate(bytes[i].toInt(), value)
        }
        return value
    }
}
