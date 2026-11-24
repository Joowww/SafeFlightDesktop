package org.safeflight.android.mavlink;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * Incremental MAVLink v1/v2 stream parser.
 *
 * <p>Bytes may arrive in arbitrary fragments (UDP datagrams usually carry whole
 * frames, but serial or TCP transports do not). A candidate frame is accepted
 * only when its message id is supported and its CRC (including CRC_EXTRA)
 * matches. Otherwise only the start byte is discarded and scanning resumes, so
 * a false start byte never swallows the next valid frame.
 *
 * <p>Frames of unsupported message ids cannot be CRC-validated (their CRC_EXTRA
 * is unknown) and are counted in {@link Stats#unsupportedOrInvalid}.
 */
public final class MavlinkParser {
    public static final int STX_V1 = 0xFE;
    public static final int STX_V2 = 0xFD;
    private static final int V1_HEADER = 6;
    private static final int V2_HEADER = 10;
    private static final int CRC_LENGTH = 2;
    private static final int SIGNATURE_LENGTH = 13;

    /** Parser counters (immutable snapshot). */
    public static final class Stats {
        public final long framesAccepted;
        public final long unsupportedOrInvalid;
        public final long bytesDiscarded;

        Stats(long framesAccepted, long unsupportedOrInvalid, long bytesDiscarded) {
            this.framesAccepted = framesAccepted;
            this.unsupportedOrInvalid = unsupportedOrInvalid;
            this.bytesDiscarded = bytesDiscarded;
        }
    }

    /** Outcome of trying to read one frame at a given position. */
    private enum Kind { NEED_MORE, INVALID, VALID }

    private static final class Attempt {
        final Kind kind;
        final int frameLength;
        final MavlinkMessage message;

        Attempt(Kind kind, int frameLength, MavlinkMessage message) {
            this.kind = kind;
            this.frameLength = frameLength;
            this.message = message;
        }
    }

    private static final Attempt NEED_MORE = new Attempt(Kind.NEED_MORE, 0, null);
    private static final Attempt INVALID = new Attempt(Kind.INVALID, 0, null);

    private byte[] buffer = new byte[4096];
    private int length = 0;
    private long framesAccepted = 0;
    private long unsupportedOrInvalid = 0;
    private long bytesDiscarded = 0;

    public Stats getStats() {
        return new Stats(framesAccepted, unsupportedOrInvalid, bytesDiscarded);
    }

    public void reset() {
        length = 0;
        framesAccepted = 0;
        unsupportedOrInvalid = 0;
        bytesDiscarded = 0;
    }

    public List<MavlinkMessage> feed(byte[] data) {
        return feed(data, 0, data.length);
    }

    /** Appends {@code count} bytes and returns every complete, valid message found so far. */
    public List<MavlinkMessage> feed(byte[] data, int offset, int count) {
        ensureCapacity(length + count);
        System.arraycopy(data, offset, buffer, length, count);
        length += count;
        List<MavlinkMessage> out = new ArrayList<>(4);
        int pos = 0;
        while (true) {
            // Find the next start byte.
            while (pos < length && !isStx(buffer[pos])) {
                pos++;
                bytesDiscarded++;
            }
            if (pos >= length) {
                break;
            }
            Attempt result = tryParse(pos);
            if (result.kind == Kind.NEED_MORE) {
                break;
            } else if (result.kind == Kind.INVALID) {
                unsupportedOrInvalid++;
                bytesDiscarded++;
                pos += 1;
            } else {
                framesAccepted++;
                if (result.message != null) {
                    out.add(result.message);
                }
                pos += result.frameLength;
            }
        }
        compact(pos);
        return out;
    }

    private Attempt tryParse(int start) {
        int available = length - start;
        int stx = u8(start);
        if (available < 2) {
            return NEED_MORE;
        }
        int payloadLength = u8(start + 1);

        if (stx == STX_V1) {
            int frameLength = V1_HEADER + payloadLength + CRC_LENGTH;
            if (available < frameLength) {
                return NEED_MORE;
            }
            return validate(start, 1, u8(start + 2), u8(start + 3), u8(start + 4), u8(start + 5),
                    start + V1_HEADER, payloadLength, frameLength, V1_HEADER - 1);
        }

        if (available < V2_HEADER) {
            return NEED_MORE;
        }
        int incompatFlags = u8(start + 2);
        if ((incompatFlags & ~0x01) != 0) {
            return INVALID; // unknown incompatibility flags
        }
        int signatureLength = (incompatFlags & 0x01) != 0 ? SIGNATURE_LENGTH : 0;
        int frameLength = V2_HEADER + payloadLength + CRC_LENGTH + signatureLength;
        if (available < frameLength) {
            return NEED_MORE;
        }
        int msgId = u8(start + 7) | (u8(start + 8) << 8) | (u8(start + 9) << 16);
        return validate(start, 2, u8(start + 4), u8(start + 5), u8(start + 6), msgId,
                start + V2_HEADER, payloadLength, frameLength, V2_HEADER - 1);
    }

    private Attempt validate(int start, int version, int seq, int sys, int comp, int msgId,
                             int payloadStart, int payloadLength, int frameLength, int headerBytesForCrc) {
        Integer crcExtra = MavlinkIds.crcExtra(msgId);
        if (crcExtra == null) {
            return INVALID;
        }
        int crc = MavlinkCrc.compute(buffer, start + 1, headerBytesForCrc + payloadLength);
        crc = MavlinkCrc.accumulate(crcExtra, crc);
        int crcPos = payloadStart + payloadLength;
        int received = u8(crcPos) | (u8(crcPos + 1) << 8);
        if (crc != received) {
            return INVALID;
        }
        byte[] payload = Arrays.copyOfRange(buffer, payloadStart, payloadStart + payloadLength);
        MavlinkHeader header = new MavlinkHeader(version, seq, sys, comp, msgId);
        return new Attempt(Kind.VALID, frameLength, MavlinkDecoder.decode(header, payload));
    }

    private static boolean isStx(byte b) {
        int v = b & 0xFF;
        return v == STX_V1 || v == STX_V2;
    }

    private int u8(int index) {
        return buffer[index] & 0xFF;
    }

    private void compact(int consumed) {
        if (consumed <= 0) {
            return;
        }
        int remaining = length - consumed;
        if (remaining > 0) {
            System.arraycopy(buffer, consumed, buffer, 0, remaining);
        }
        length = remaining;
    }

    private void ensureCapacity(int required) {
        if (required > buffer.length) {
            buffer = Arrays.copyOf(buffer, Math.max(required, buffer.length * 2));
        }
    }
}
