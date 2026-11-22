package org.safeflight.android.mavlink

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MavlinkParserTest {

    @Test
    fun crcMatchesReferenceValue() {
        // CRC-16/MCRF4XX check value for "123456789" is 0x6F91.
        val data = "123456789".toByteArray()
        assertEquals(0x6F91, MavlinkCrc.compute(data, 0, data.size))
    }

    @Test
    fun gcsHeartbeatRoundTrips() {
        val encoder = GcsHeartbeatEncoder()
        val frame = encoder.encode()
        val messages = MavlinkParser().feed(frame)
        assertEquals(1, messages.size)
        val hb = messages.first() as MavlinkMessage.Heartbeat
        assertEquals(255, hb.header.systemId)
        assertEquals(MavConstants.MAV_TYPE_GCS, hb.type)
        assertEquals(false, hb.isVehicle)
        assertEquals(false, hb.armed)
        // Sequence increments per frame.
        assertEquals(1, MavlinkParser().feed(encoder.encode()).first().header.sequence)
    }

    @Test
    fun framesSplitAcrossChunksAreReassembled() {
        val frame = GcsHeartbeatEncoder().encode()
        val parser = MavlinkParser()
        var out = emptyList<MavlinkMessage>()
        for (b in frame) out = out + parser.feed(byteArrayOf(b))
        assertEquals(1, out.size)
    }

    @Test
    fun falseStartDoesNotSwallowNextFrame() {
        // Stricter than pymavlink: only the false start byte is dropped.
        val frame = GcsHeartbeatEncoder().encode()
        val data = byteArrayOf(0xFD.toByte(), 0x01) + frame
        val out = MavlinkParser().feed(data)
        assertEquals(1, out.size)
    }

    @Test
    fun unsupportedMessagesAreSkippedWithoutLosingSync() {
        // Frame with unknown message id 9999 followed by a valid heartbeat.
        val unknown = byteArrayOf(0xFD.toByte(), 3, 0, 0, 0, 1, 1, 0x0F, 0x27, 0, 1, 2, 3, 0x11, 0x22)
        val out = MavlinkParser().feed(unknown + GcsHeartbeatEncoder().encode())
        assertEquals(1, out.size)
        assertTrue(out.first() is MavlinkMessage.Heartbeat)
    }

    @Test
    fun encoderProducesOnlyHeartbeats() {
        val frame = GcsHeartbeatEncoder().encode()
        assertArrayEquals(byteArrayOf(0, 0, 0), frame.copyOfRange(7, 10)) // msgid 0 = HEARTBEAT
    }
}
