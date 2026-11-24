package org.safeflight.android.mavlink

/**
 * Incremental MAVLink v1/v2 stream parser.
 *
 * Bytes may arrive in arbitrary fragments (UDP datagrams usually carry whole
 * frames, but serial or TCP transports do not). A candidate frame is accepted
 * only when its message id is supported and its CRC (including CRC_EXTRA)
 * matches. Otherwise only the start byte is discarded and scanning resumes,
 * so a false start byte never swallows the next valid frame.
 *
 * Frames of unsupported message ids cannot be CRC-validated (their CRC_EXTRA
 * is unknown) and are counted as [Stats.unsupportedOrInvalid].
 */
class MavlinkParser {

    data class Stats(
        val framesAccepted: Long = 0,
        val unsupportedOrInvalid: Long = 0,
        val bytesDiscarded: Long = 0,
    )

    private var buffer = ByteArray(4096)
    private var length = 0
    var stats = Stats()
        private set

    fun reset() {
        length = 0
        stats = Stats()
    }

    /** Appends [data] and returns every complete, valid message found so far. */
    fun feed(data: ByteArray, offset: Int = 0, count: Int = data.size): List<MavlinkMessage> {
        ensureCapacity(length + count)
        System.arraycopy(data, offset, buffer, length, count)
        length += count
        val out = ArrayList<MavlinkMessage>(4)
        var pos = 0
        while (true) {
            // Find next start byte.
            while (pos < length && !isStx(buffer[pos])) {
                pos++
                stats = stats.copy(bytesDiscarded = stats.bytesDiscarded + 1)
            }
            if (pos >= length) break
            val result = tryParse(pos)
            when (result) {
                is Attempt.NeedMore -> break
                is Attempt.Invalid -> {
                    stats = stats.copy(
                        unsupportedOrInvalid = stats.unsupportedOrInvalid + 1,
                        bytesDiscarded = stats.bytesDiscarded + 1,
                    )
                    pos += 1
                }
                is Attempt.Valid -> {
                    stats = stats.copy(framesAccepted = stats.framesAccepted + 1)
                    result.message?.let(out::add)
                    pos += result.frameLength
                }
            }
        }
        compact(pos)
        return out
    }

    private sealed interface Attempt {
        data object NeedMore : Attempt
        data object Invalid : Attempt
        data class Valid(val frameLength: Int, val message: MavlinkMessage?) : Attempt
    }

    private fun tryParse(start: Int): Attempt {
        val available = length - start
        val stx = buffer[start].toInt() and 0xFF
        if (available < 2) return Attempt.NeedMore
        val payloadLength = buffer[start + 1].toInt() and 0xFF

        if (stx == STX_V1) {
            val frameLength = V1_HEADER + payloadLength + CRC_LENGTH
            if (available < frameLength) return Attempt.NeedMore
            val seq = u8(start + 2)
            val sys = u8(start + 3)
            val comp = u8(start + 4)
            val msgId = u8(start + 5)
            val payloadStart = start + V1_HEADER
            return validate(start, 1, seq, sys, comp, msgId, payloadStart, payloadLength, frameLength, V1_HEADER - 1)
        }

        if (available < V2_HEADER) return Attempt.NeedMore
        val incompatFlags = u8(start + 2)
        if (incompatFlags and 0x01.inv() != 0) return Attempt.Invalid // unknown incompatibility flags
        val signatureLength = if (incompatFlags and 0x01 != 0) SIGNATURE_LENGTH else 0
        val frameLength = V2_HEADER + payloadLength + CRC_LENGTH + signatureLength
        if (available < frameLength) return Attempt.NeedMore
        val seq = u8(start + 4)
        val sys = u8(start + 5)
        val comp = u8(start + 6)
        val msgId = u8(start + 7) or (u8(start + 8) shl 8) or (u8(start + 9) shl 16)
        val payloadStart = start + V2_HEADER
        return validate(start, 2, seq, sys, comp, msgId, payloadStart, payloadLength, frameLength, V2_HEADER - 1)
    }

    private fun validate(
        start: Int, version: Int, seq: Int, sys: Int, comp: Int, msgId: Int,
        payloadStart: Int, payloadLength: Int, frameLength: Int, headerBytesForCrc: Int,
    ): Attempt {
        val crcExtra = MavlinkIds.CRC_EXTRA[msgId] ?: return Attempt.Invalid
        var crc = MavlinkCrc.compute(buffer, start + 1, headerBytesForCrc + payloadLength)
        crc = MavlinkCrc.accumulate(crcExtra, crc)
        val crcPos = payloadStart + payloadLength
        val received = u8(crcPos) or (u8(crcPos + 1) shl 8)
        if (crc != received) return Attempt.Invalid
        val payload = buffer.copyOfRange(payloadStart, payloadStart + payloadLength)
        val header = MavlinkHeader(version, seq, sys, comp, msgId)
        return Attempt.Valid(frameLength, MavlinkDecoder.decode(header, payload))
    }

    private fun isStx(b: Byte): Boolean {
        val v = b.toInt() and 0xFF
        return v == STX_V1 || v == STX_V2
    }

    private fun u8(index: Int): Int = buffer[index].toInt() and 0xFF

    private fun compact(consumed: Int) {
        if (consumed <= 0) return
        val remaining = length - consumed
        if (remaining > 0) System.arraycopy(buffer, consumed, buffer, 0, remaining)
        length = remaining
    }

    private fun ensureCapacity(required: Int) {
        if (required > buffer.size) buffer = buffer.copyOf(maxOf(required, buffer.size * 2))
    }

    companion object {
        const val STX_V1 = 0xFE
        const val STX_V2 = 0xFD
        private const val V1_HEADER = 6
        private const val V2_HEADER = 10
        private const val CRC_LENGTH = 2
        private const val SIGNATURE_LENGTH = 13
    }
}
