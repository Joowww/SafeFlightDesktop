package org.safeflight.android.mavlink;

/** Header fields of a received MAVLink frame (v1 or v2). Immutable. */
public final class MavlinkHeader {
    public final int version;
    public final int sequence;
    public final int systemId;
    public final int componentId;
    public final int messageId;

    public MavlinkHeader(int version, int sequence, int systemId, int componentId, int messageId) {
        this.version = version;
        this.sequence = sequence;
        this.systemId = systemId;
        this.componentId = componentId;
        this.messageId = messageId;
    }
}
