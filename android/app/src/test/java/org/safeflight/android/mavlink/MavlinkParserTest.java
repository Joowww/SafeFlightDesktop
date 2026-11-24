package org.safeflight.android.mavlink;

import org.junit.Test;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class MavlinkParserTest {

    private static byte[] concat(byte[] a, byte[] b) {
        byte[] out = Arrays.copyOf(a, a.length + b.length);
        System.arraycopy(b, 0, out, a.length, b.length);
        return out;
    }

    @Test
    public void crcMatchesReferenceValue() {
        // CRC-16/MCRF4XX check value for "123456789" is 0x6F91.
        byte[] data = "123456789".getBytes(StandardCharsets.US_ASCII);
        assertEquals(0x6F91, MavlinkCrc.compute(data, 0, data.length));
    }

    @Test
    public void gcsHeartbeatRoundTrips() {
        GcsHeartbeatEncoder encoder = new GcsHeartbeatEncoder();
        List<MavlinkMessage> messages = new MavlinkParser().feed(encoder.encode());
        assertEquals(1, messages.size());
        MavlinkMessage.Heartbeat hb = (MavlinkMessage.Heartbeat) messages.get(0);
        assertEquals(255, hb.header.systemId);
        assertEquals(MavConstants.MAV_TYPE_GCS, hb.type);
        assertFalse(hb.isVehicle());
        assertFalse(hb.isArmed());
        // Sequence increments per frame.
        assertEquals(1, new MavlinkParser().feed(encoder.encode()).get(0).header.sequence);
    }

    @Test
    public void framesSplitAcrossChunksAreReassembled() {
        byte[] frame = new GcsHeartbeatEncoder().encode();
        MavlinkParser parser = new MavlinkParser();
        List<MavlinkMessage> out = new ArrayList<>();
        for (byte b : frame) {
            out.addAll(parser.feed(new byte[] {b}));
        }
        assertEquals(1, out.size());
    }

    @Test
    public void falseStartDoesNotSwallowNextFrame() {
        // Stricter than pymavlink: only the false start byte is dropped.
        byte[] data = concat(new byte[] {(byte) 0xFD, 0x01}, new GcsHeartbeatEncoder().encode());
        assertEquals(1, new MavlinkParser().feed(data).size());
    }

    @Test
    public void unsupportedMessagesAreSkippedWithoutLosingSync() {
        // Frame with unknown message id 9999 followed by a valid heartbeat.
        byte[] unknown = {(byte) 0xFD, 3, 0, 0, 0, 1, 1, 0x0F, 0x27, 0, 1, 2, 3, 0x11, 0x22};
        List<MavlinkMessage> out = new MavlinkParser().feed(concat(unknown, new GcsHeartbeatEncoder().encode()));
        assertEquals(1, out.size());
        assertTrue(out.get(0) instanceof MavlinkMessage.Heartbeat);
    }

    @Test
    public void encoderProducesOnlyHeartbeats() {
        byte[] frame = new GcsHeartbeatEncoder().encode();
        assertArrayEquals(new byte[] {0, 0, 0}, Arrays.copyOfRange(frame, 7, 10)); // msgid 0 = HEARTBEAT
    }
}
